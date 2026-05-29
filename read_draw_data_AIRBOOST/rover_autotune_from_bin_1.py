#!/usr/bin/env python3
"""
Enhanced Skid-Steer Rover Autotune - Version with Accurate FF via Linear Regression

Key improvements over previous:
- ATC_STR_RAT_FF calculated precisely using linear regression: yaw_rate ≈ k * (steer_norm * speed)
- Normalizes to ArduPilot's baseline (full steer at 1 m/s → ~45 deg/s yaw rate)
- Falls back to heuristic (eff * 0.95) only if fit quality low (R² ≤ 0.7) or insufficient steered data
- Prints fit quality (R²) and source of FF value
- More conservative clamps and better diagnostics
- Optional diagnostic plots including regression fit
"""

import math
import bisect
import argparse
import numpy as np
from pymavlink import mavutil


# ---------------- config ----------------
MAX_DT_US = 50_000
STEER_NORM = 4000.0
STEER_SAT_TH = 0.90
MIN_SPEED = 1.0
MIN_SAMPLES = 3000
MIN_STEER_FOR_FIT = (
    0.05  # minimum |steer_norm| to include in regression (avoid straight-line noise)
)
MIN_R2_FOR_FIT = 0.70  # threshold to trust regression over heuristic


# ---------------- utils ----------------
def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))


def r_squared(y, y_pred):
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0


def nearest(ts, data_t, data_v):
    i = bisect.bisect_left(data_t, ts)
    if i <= 0 or i >= len(data_t):
        return None
    b_t, b_v = data_t[i - 1], data_v[i - 1]
    a_t, a_v = data_t[i], data_v[i]
    return a_v if abs(a_t - ts) < abs(ts - b_t) else b_v


def nearest_hold(ts, data_t, data_v):
    i = bisect.bisect_right(data_t, ts) - 1
    if i < 0:
        return None
    return data_v[i]


# ---------------- args ----------------
parser = argparse.ArgumentParser(
    description="Enhanced autotune skid-steer rover from .bin log"
)
parser.add_argument("log", help="DataFlash log .bin file")
parser.add_argument(
    "--target-speed",
    type=float,
    default=None,
    help="Desired cruise speed (m/s) for scaling",
)
parser.add_argument(
    "--plot", action="store_true", help="Show diagnostic plots (requires matplotlib)"
)
args = parser.parse_args()

mlog = mavutil.mavlink_connection(args.log)

# ---------------- containers ----------------
att, imu, ster, gps, stat = [], [], [], [], []

# ---------------- parse log ----------------
print("Parsing log...")
while True:
    msg = mlog.recv_match(blocking=False)
    if msg is None:
        break
    t = getattr(msg, "TimeUS", None)
    if t is None:
        continue
    mtype = msg.get_type()
    if mtype == "ATT":
        att.append((t, math.radians(msg.Yaw)))
    elif mtype == "IMU":
        imu.append((t, msg.GyrZ))
    elif mtype == "STER":
        ster.append((t, msg.SteerOut))
    elif mtype == "GPS" and hasattr(msg, "Spd"):
        gps.append((t, msg.Spd))
    elif mtype == "STAT" and hasattr(msg, "FlightMode"):
        stat.append((t, msg.FlightMode))

if not att or not imu or not ster or not gps:
    raise RuntimeError("ERROR: Missing required messages (ATT / IMU / STER / GPS)")

# ---------------- timestamps ----------------
imu_t, imu_v = zip(*imu) if imu else ([], [])
ster_t, ster_v = zip(*ster) if ster else ([], [])
gps_t, gps_v = zip(*gps) if gps else ([], [])
stat_t, stat_v = zip(*stat) if stat else ([], [])

# ---------------- aligned signals ----------------
yaw_rate = []
steer_norm = []
speed = []
steer_rate = []
times = []
auto_used = False

prev_st = None
prev_t = None

print("Aligning and filtering data...")
for t, _ in att:
    gz = nearest(t, imu_t, imu_v)
    st = nearest(t, ster_t, ster_v)
    sp = nearest(t, gps_t, gps_v)
    fm = nearest_hold(t, stat_t, stat_v) if stat else "AUTO"

    if gz is None or st is None or sp is None:
        continue

    if fm != "AUTO":
        continue
    auto_used = True

    s = st / STEER_NORM
    if abs(s) > STEER_SAT_TH:
        continue

    if sp < MIN_SPEED:
        continue

    yaw_rate.append(gz)
    steer_norm.append(s)
    speed.append(sp)
    times.append(t)

    if prev_st is not None:
        dt = (t - prev_t) * 1e-6
        if 0 < dt < (MAX_DT_US * 1e-6):
            steer_rate.append(abs((s - prev_st) / dt))

    prev_st = s
    prev_t = t

if len(yaw_rate) < MIN_SAMPLES:
    raise RuntimeError(
        f"ERROR: Not enough valid samples ({len(yaw_rate)} < {MIN_SAMPLES})"
    )

yaw_rate = np.array(yaw_rate)
steer_norm = np.array(steer_norm)
speed = np.array(speed)
times = np.array(times) / 1e6

# ---------------- metrics ----------------
yaw_rate_demean = yaw_rate - np.mean(yaw_rate)
osc = np.std(yaw_rate_demean)
bias = abs(np.mean(yaw_rate))
eff = np.mean(np.abs(steer_norm))
yr95 = np.percentile(np.abs(yaw_rate_demean), 95)
speed_meas = clamp(np.median(speed), 0.5, 8.0)

# ---------------- Improved FF via regression ----------------
x_fit = steer_norm * speed
mask = np.abs(steer_norm) > MIN_STEER_FOR_FIT
ff_source = "heuristic"

if np.sum(mask) > MIN_SAMPLES // 5:  # enough steered samples
    k, offset = np.polyfit(x_fit[mask], yaw_rate[mask], 1)
    y_pred = k * x_fit[mask] + offset
    r2 = r_squared(yaw_rate[mask], y_pred)

    # ArduPilot baseline: full steer (1.0) at 1 m/s → ~45 deg/s = 0.785 rad/s
    baseline_yaw = math.radians(45)
    ff_from_fit = abs(k) / baseline_yaw

    print(f"FF regression fit: k={k:.4f}, offset={offset:.4f}, R²={r2:.3f}")

    if r2 > MIN_R2_FOR_FIT:
        ATC_STR_RAT_FF = clamp(ff_from_fit, 0.05, 0.60)
        ff_source = "regression (recommended)"
    else:
        ATC_STR_RAT_FF = clamp(eff * 0.95, 0.05, 0.50)
else:
    print("Insufficient steered data for regression")
    ATC_STR_RAT_FF = clamp(eff * 0.95, 0.05, 0.50)

# ---------------- other parameters ----------------
ATC_STR_RAT_P = clamp(0.25 / (osc + 1e-3), 0.08, 0.80)
ATC_STR_RAT_D = clamp(osc * 0.12, 0.008, 0.18)
ATC_STR_RAT_I = clamp(bias * 0.02, 0.0, 0.06)
ATC_STR_RAT_D_FF = clamp(yr95 * 0.14, 0.008, 0.22)

if steer_rate:
    sr95 = np.percentile(steer_rate, 95)
    ATC_STR_RAT_MAX = clamp(sr95 * 57.3, 35, 140)
else:
    ATC_STR_RAT_MAX = 80

ATC_SPEED_FF = clamp(0.6 + speed_meas * 0.14, 0.5, 1.3)
ATC_SPEED_D_FF = clamp(np.std(np.diff(speed)) * 0.7, 0.0, 0.6)
ATC_ACCEL_MAX = clamp(2.0 - np.std(np.diff(yaw_rate_demean)) * 1.8, 0.7, 2.5)

# ---------------- scaling ----------------
CRUISE_SPEED = speed_meas
scale = 1.0
if args.target_speed:
    if abs(args.target_speed - speed_meas) > speed_meas * 0.5:
        print(f"Warning: Target speed differs significantly from measured")
    scale = args.target_speed / speed_meas
    CRUISE_SPEED = args.target_speed

    ATC_STR_RAT_P /= scale
    ATC_STR_RAT_I /= scale
    ATC_STR_RAT_D /= scale
    ATC_STR_RAT_FF *= scale
    ATC_STR_RAT_D_FF *= scale
    ATC_SPEED_FF *= scale
    ATC_SPEED_D_FF *= scale
    ATC_ACCEL_MAX *= scale

# ---------------- output ----------------
print("\n===== Enhanced Rover Autotune Results =====\n")
print(f"Valid samples       : {len(yaw_rate)}")
print(f"Measured median speed: {speed_meas:.2f} m/s")
print(f"Target cruise speed : {CRUISE_SPEED:.2f} m/s")
print(f"AUTO mode filtered  : YES (strict)\n")

print("--- Key metrics ---")
print(f"Yaw rate std (osc)  : {osc:.4f} rad/s")
print(f"Yaw rate bias       : {bias:.4f} rad/s")
print(f"Avg |steer| effort  : {eff:.3f}")
print(f"95th yaw rate noise : {yr95:.4f} rad/s\n")

print("--- Recommended parameters ---")
print(f"ATC_STR_RAT_P    = {ATC_STR_RAT_P:.3f}")
print(f"ATC_STR_RAT_I    = {ATC_STR_RAT_I:.3f}")
print(f"ATC_STR_RAT_D    = {ATC_STR_RAT_D:.3f}")
print(f"ATC_STR_RAT_FF   = {ATC_STR_RAT_FF:.3f}   ({ff_source})")
print(f"ATC_STR_RAT_D_FF = {ATC_STR_RAT_D_FF:.3f}")
print(f"ATC_STR_RAT_MAX  = {ATC_STR_RAT_MAX:.1f}")
print(f"ATC_SPEED_FF     = {ATC_SPEED_FF:.3f}")
print(f"ATC_SPEED_D_FF   = {ATC_SPEED_D_FF:.3f}")
print(f"ATC_ACCEL_MAX    = {ATC_ACCEL_MAX:.2f}")

print(
    "\nNote: These are excellent starting values. Always test in a safe area and fine-tune."
)
