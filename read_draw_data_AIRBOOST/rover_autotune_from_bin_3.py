#!/usr/bin/env python3
"""
Physics-based Full Autotune for Skid-Steer Rover (ArduPilot)

Autotunes:
  - Steering Rate PID + FF (yaw-rate domain)
  - Speed / Throttle PID + FF (longitudinal dynamics)

Key models:
  yaw_rate ≈ k_s * steer_norm * speed
  dv/dt     ≈ k_t * throttle_norm - k_d * speed

Author intent:
  - Academic rigor
  - Production-safety clamps
  - Regression quality checks
"""

import math
import bisect
import argparse
import numpy as np
from pymavlink import mavutil


# ===================== CONFIG =====================

STEER_NORM = 4000.0
STEER_SAT_TH = 0.90
MIN_SPEED = 1.0
MIN_SAMPLES = 3000
MIN_STEER_FOR_FIT = 0.05
MIN_R2_FOR_FIT = 0.70
MAX_DT_US = 50_000

# ================================================


def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))


def r_squared(y, y_hat):
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def nearest(ts, t, v):
    i = bisect.bisect_left(t, ts)
    if i <= 0 or i >= len(t):
        return None
    return v[i] if abs(t[i] - ts) < abs(ts - t[i - 1]) else v[i - 1]


def nearest_hold(ts, t, v):
    i = bisect.bisect_right(t, ts) - 1
    return v[i] if i >= 0 else None


# ===================== ARGUMENTS =====================

parser = argparse.ArgumentParser("Full Rover Autotune")
parser.add_argument("log", help="ArduPilot DataFlash log (.bin)")
parser.add_argument("--target-speed", type=float, default=None)
args = parser.parse_args()

mlog = mavutil.mavlink_connection(args.log)

# ===================== LOG PARSING =====================

att, imu, ster, gps, stat, thr = [], [], [], [], [], []

print("Parsing log...")
while True:
    msg = mlog.recv_match(blocking=False)
    if msg is None:
        break
    t = getattr(msg, "TimeUS", None)
    if t is None:
        continue

    m = msg.get_type()

    if m == "ATT":
        att.append((t, math.radians(msg.Yaw)))
    elif m == "IMU":
        imu.append((t, msg.GyrZ))
    elif m == "STER":
        ster.append((t, msg.SteerOut))
    elif m == "GPS" and hasattr(msg, "Spd"):
        gps.append((t, msg.Spd))
    elif m == "STAT" and hasattr(msg, "FlightMode"):
        stat.append((t, msg.FlightMode))
    elif m in ("CTUN", "THR") and hasattr(msg, "ThO"):
        thr.append((t, msg.ThO))

if not (att and imu and ster and gps and thr):
    raise RuntimeError("ERROR: Missing required messages")

imu_t, imu_v = zip(*imu)
ster_t, ster_v = zip(*ster)
gps_t, gps_v = zip(*gps)
thr_t, thr_v = zip(*thr)
stat_t, stat_v = zip(*stat) if stat else ([], [])

# ===================== SIGNAL ALIGNMENT =====================

yaw_rate, steer_norm, speed, throttle = [], [], [], []
times = []

print("Aligning and filtering...")
for t, _ in att:
    gz = nearest(t, imu_t, imu_v)
    st = nearest(t, ster_t, ster_v)
    sp = nearest(t, gps_t, gps_v)
    th = nearest(t, thr_t, thr_v)
    fm = nearest_hold(t, stat_t, stat_v) if stat else "AUTO"

    if None in (gz, st, sp, th):
        continue
    if fm != "AUTO":
        continue

    s = st / STEER_NORM
    if abs(s) > STEER_SAT_TH or sp < MIN_SPEED:
        continue

    yaw_rate.append(gz)
    steer_norm.append(s)
    speed.append(sp)
    throttle.append(th / 100.0)
    times.append(t * 1e-6)

if len(yaw_rate) < MIN_SAMPLES:
    raise RuntimeError("ERROR: insufficient valid data")

yaw_rate = np.array(yaw_rate)
steer_norm = np.array(steer_norm)
speed = np.array(speed)
throttle = np.array(throttle)
times = np.array(times)

# ===================== STEERING AUTOTUNE =====================

yaw_demean = yaw_rate - np.mean(yaw_rate)
osc = np.std(yaw_demean)
bias = abs(np.mean(yaw_rate))
yr95 = np.percentile(np.abs(yaw_demean), 95)
eff = np.mean(np.abs(steer_norm))
speed_med = clamp(np.median(speed), 0.5, 8.0)

# --- FF via regression ---
x = steer_norm * speed
mask = np.abs(steer_norm) > MIN_STEER_FOR_FIT

if np.sum(mask) > MIN_SAMPLES // 5:
    k, b = np.polyfit(x[mask], yaw_rate[mask], 1)
    r2 = r_squared(yaw_rate[mask], k * x[mask] + b)
    baseline = math.radians(45)
    if r2 > MIN_R2_FOR_FIT:
        ATC_STR_RAT_FF = clamp(abs(k) / baseline, 0.05, 0.60)
        ff_src = "regression"
    else:
        ATC_STR_RAT_FF = clamp(eff * 0.95, 0.05, 0.50)
        ff_src = "heuristic"
else:
    ATC_STR_RAT_FF = clamp(eff * 0.95, 0.05, 0.50)
    ff_src = "heuristic"

ATC_STR_RAT_P = clamp(0.25 / (osc + 1e-3), 0.08, 0.80)
ATC_STR_RAT_D = clamp(osc * 0.12, 0.008, 0.18)
ATC_STR_RAT_I = clamp(bias * 0.02, 0.0, 0.06)
ATC_STR_RAT_D_FF = clamp(yr95 * 0.14, 0.008, 0.22)
ATC_STR_RAT_MAX = clamp(np.percentile(np.abs(np.diff(steer_norm)), 95) * 60, 35, 140)

# ===================== SPEED AUTOTUNE =====================

dv = np.diff(speed) / np.diff(times)
v_mid = speed[:-1]
u_mid = throttle[:-1]

A = np.vstack([u_mid, -v_mid]).T
k_t, k_d = np.linalg.lstsq(A, dv, rcond=None)[0]

tau_v = 1.0 / max(k_d, 1e-3)
wc = 1.0 / (2.0 * tau_v)

ATC_SPEED_P = clamp(wc / max(k_t, 1e-3), 0.05, 1.0)
ATC_SPEED_I = clamp((k_d * wc) / max(k_t, 1e-3), 0.02, 0.5)
ATC_SPEED_D = 0.0
ATC_SPEED_IMAX = 0.30

ATC_SPEED_FF = clamp(1.0 / max(k_t, 1e-3), 0.5, 1.5)
ATC_SPEED_D_FF = clamp(np.std(dv) * 0.5, 0.0, 0.6)
ATC_ACCEL_MAX = clamp(2.0 - np.std(dv) * 2.0, 0.5, 2.5)

# ===================== SCALING =====================

CRUISE_SPEED = speed_med
if args.target_speed:
    scale = args.target_speed / speed_med
    CRUISE_SPEED = args.target_speed

    ATC_STR_RAT_P /= scale
    ATC_STR_RAT_I /= scale
    ATC_STR_RAT_D /= scale
    ATC_STR_RAT_FF *= scale

    ATC_SPEED_P *= scale
    ATC_SPEED_I *= scale
    ATC_SPEED_FF *= scale
    ATC_ACCEL_MAX *= scale

# ===================== OUTPUT =====================

print("\n===== FULL AUTOTUNE RESULTS =====\n")

print("--- Steering Rate ---")
print(f"ATC_STR_RAT_P    = {ATC_STR_RAT_P:.3f}")
print(f"ATC_STR_RAT_I    = {ATC_STR_RAT_I:.3f}")
print(f"ATC_STR_RAT_D    = {ATC_STR_RAT_D:.3f}")
print(f"ATC_STR_RAT_FF   = {ATC_STR_RAT_FF:.3f} ({ff_src})")
print(f"ATC_STR_RAT_D_FF = {ATC_STR_RAT_D_FF:.3f}")
print(f"ATC_STR_RAT_MAX  = {ATC_STR_RAT_MAX:.1f}")

print("\n--- Speed / Throttle ---")
print(f"ATC_SPEED_P      = {ATC_SPEED_P:.3f}")
print(f"ATC_SPEED_I      = {ATC_SPEED_I:.3f}")
print(f"ATC_SPEED_IMAX   = {ATC_SPEED_IMAX:.2f}")
print(f"ATC_SPEED_D      = {ATC_SPEED_D:.3f}")
print(f"ATC_SPEED_FF     = {ATC_SPEED_FF:.3f}")
print(f"ATC_SPEED_D_FF   = {ATC_SPEED_D_FF:.3f}")
print(f"ATC_ACCEL_MAX    = {ATC_ACCEL_MAX:.2f}")

print(f"\nCRUISE_SPEED     = {CRUISE_SPEED:.2f} m/s")
print("\nNOTE: Apply conservatively and validate in open area.")
