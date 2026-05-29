#!/usr/bin/env python3
"""
Final Skid-Steer Rover Autotune (Physics-based, Production-ready)

Input  : ArduPilot DataFlash .bin
Output : Recommended parameters
- ATC_STR_RAT_P / I / D
- ATC_STR_RAT_FF
- ATC_STR_RAT_D_FF
- ATC_STR_RAT_MAX
- ATC_SPEED_FF
- ATC_SPEED_D_FF
- ATC_ACCEL_MAX
- CRUISE_SPEED

Interface compatible with original script
"""

import math
import bisect
import argparse
import numpy as np
from pymavlink import mavutil

# ---------------- config ----------------
MAX_DT_US = 50_000
STEER_NORM = 4000.0
STEER_SAT = 0.90
MIN_SPEED = 1.0
MIN_SAMPLES = 3000
MIN_STEER_FOR_FIT = 0.05
MIN_R2 = 0.70

BASELINE_YAW = math.radians(45.0)  # 45 deg/s @ full steer, 1 m/s


# ---------------- utils ----------------
def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))


def nearest(ts, t_arr, v_arr):
    i = bisect.bisect_left(t_arr, ts)
    if i <= 0 or i >= len(t_arr):
        return None
    if abs(t_arr[i] - ts) < abs(ts - t_arr[i - 1]):
        return v_arr[i]
    return v_arr[i - 1]


def nearest_hold(ts, t_arr, v_arr):
    i = bisect.bisect_right(t_arr, ts) - 1
    if i < 0:
        return None
    return v_arr[i]


def r2_score(y, yhat):
    ssr = np.sum((y - yhat) ** 2)
    sst = np.sum((y - np.mean(y)) ** 2)
    return 1 - ssr / sst if sst > 0 else 0


# ---------------- args ----------------
parser = argparse.ArgumentParser()
parser.add_argument("log", help="DataFlash log .bin")
parser.add_argument(
    "--target-speed", type=float, default=None, help="Desired cruise speed (m/s)"
)
args = parser.parse_args()

# ---------------- parse log ----------------
mlog = mavutil.mavlink_connection(args.log)

att, imu, ster, gps, stat = [], [], [], [], []

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

if not att or not imu or not ster or not gps:
    raise RuntimeError("ERROR: Missing ATT / IMU / STER / GPS")

if not stat:
    print("Warning: STAT/FlightMode not found, AUTO filter disabled")

imu_t, imu_v = zip(*imu)
ster_t, ster_v = zip(*ster)
gps_t, gps_v = zip(*gps)
stat_t, stat_v = zip(*stat) if stat else ([], [])

# ---------------- align & filter ----------------
yaw_rate = []
steer = []
speed = []
steer_rate = []

prev_s = None
prev_t = None

for t, _ in att:
    gz = nearest(t, imu_t, imu_v)
    st = nearest(t, ster_t, ster_v)
    sp = nearest(t, gps_t, gps_v)

    if gz is None or st is None or sp is None:
        continue

    if stat:
        if nearest_hold(t, stat_t, stat_v) != "AUTO":
            continue

    s = st / STEER_NORM
    if abs(s) > STEER_SAT or sp < MIN_SPEED:
        continue

    yaw_rate.append(gz)
    steer.append(s)
    speed.append(sp)

    if prev_s is not None:
        dt = (t - prev_t) * 1e-6
        if 0 < dt < (MAX_DT_US * 1e-6):
            steer_rate.append(abs((s - prev_s) / dt))

    prev_s = s
    prev_t = t

if len(yaw_rate) < MIN_SAMPLES:
    raise RuntimeError("ERROR: not enough valid samples")

yaw_rate = np.array(yaw_rate)
steer = np.array(steer)
speed = np.array(speed)

# ---------------- metrics ----------------
yaw_d = yaw_rate - np.mean(yaw_rate)
osc = np.std(yaw_d)
bias = abs(np.mean(yaw_rate))
eff = np.mean(np.abs(steer))
yr95 = np.percentile(np.abs(yaw_d), 95)
speed_med = clamp(np.median(speed), 0.5, 8.0)

# ---------------- FF via regression ----------------
x = steer * speed
mask = np.abs(steer) > MIN_STEER_FOR_FIT
ff_source = "heuristic"

if np.sum(mask) > MIN_SAMPLES // 5:
    k, c = np.polyfit(x[mask], yaw_rate[mask], 1)
    yhat = k * x[mask] + c
    r2 = r2_score(yaw_rate[mask], yhat)

    if r2 > MIN_R2:
        ATC_STR_RAT_FF = clamp(abs(k) / BASELINE_YAW, 0.05, 0.60)
        ff_source = f"regression (R2={r2:.2f})"
    else:
        ATC_STR_RAT_FF = clamp(eff * 0.9, 0.05, 0.40)
else:
    ATC_STR_RAT_FF = clamp(eff * 0.9, 0.05, 0.40)

# ---------------- other parameters ----------------
ATC_STR_RAT_P = clamp(0.25 / (osc + 1e-3), 0.10, 0.80)
ATC_STR_RAT_D = clamp(osc * 0.12, 0.01, 0.18)
ATC_STR_RAT_I = clamp(bias * 0.02, 0.0, 0.05)

ATC_STR_RAT_D_FF = clamp(yr95 * 0.12, 0.01, 0.20)

if steer_rate:
    ATC_STR_RAT_MAX = clamp(np.percentile(steer_rate, 95) * 57.3, 30, 120)
else:
    ATC_STR_RAT_MAX = 80.0

ATC_SPEED_FF = clamp(0.6 + speed_med * 0.14, 0.6, 1.2)
ATC_SPEED_D_FF = clamp(np.std(np.diff(speed)) * 0.7, 0.0, 0.5)
ATC_ACCEL_MAX = clamp(1.6 - np.std(np.diff(yaw_d)) * 1.5, 0.8, 2.0)

# ---------------- scale ----------------
CRUISE_SPEED = speed_med
if args.target_speed:
    scale = args.target_speed / speed_med
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
print("\n===== Final Rover Autotune Results =====\n")
print(f"Samples             : {len(yaw_rate)}")
print(f"Cruise speed (m/s)   : {CRUISE_SPEED:.2f}")
print(f"FF source            : {ff_source}\n")

print("ATC_STR_RAT_P      =", round(ATC_STR_RAT_P, 3))
print("ATC_STR_RAT_I      =", round(ATC_STR_RAT_I, 3))
print("ATC_STR_RAT_D      =", round(ATC_STR_RAT_D, 3))
print("ATC_STR_RAT_FF     =", round(ATC_STR_RAT_FF, 3))
print("ATC_STR_RAT_D_FF   =", round(ATC_STR_RAT_D_FF, 3))
print("ATC_STR_RAT_MAX    =", round(ATC_STR_RAT_MAX, 1))
print("ATC_SPEED_FF       =", round(ATC_SPEED_FF, 2))
print("ATC_SPEED_D_FF     =", round(ATC_SPEED_D_FF, 2))
print("ATC_ACCEL_MAX      =", round(ATC_ACCEL_MAX, 2))
