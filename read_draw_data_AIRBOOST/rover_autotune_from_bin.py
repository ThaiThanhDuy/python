#!/usr/bin/env python3
"""
Skid-Steer Rover Autotune (ArduPilot DataFlash .bin)

Auto-tune & scale for target speed:
- ATC_STR_RAT_P / I / D
- ATC_STR_RAT_MAX
- ATC_STR_RAT_FF
- ATC_STR_RAT_D_FF
- ATC_SPEED_FF
- ATC_SPEED_D_FF
- CRUISE_SPEED
- ATC_ACCEL_MAX
"""

import sys
import math
import bisect
import argparse
import numpy as np
from pymavlink import mavutil


# ---------------- config ----------------
MAX_DT_US = 50_000
STEER_NORM = 4000.0
MIN_SAMPLES = 2000


# ---------------- utils ----------------
def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))


def normalize(x):
    x = np.asarray(x)
    return x - np.mean(x)


def nearest(ts, data_t, data_v):
    i = bisect.bisect_left(data_t, ts)
    if i == 0 or i >= len(data_t):
        return None

    b_t, b_v = data_t[i - 1], data_v[i - 1]
    a_t, a_v = data_t[i], data_v[i]

    if abs(a_t - ts) < abs(ts - b_t):
        return a_v if abs(a_t - ts) < MAX_DT_US else None
    else:
        return b_v if abs(ts - b_t) < MAX_DT_US else None


# ---------------- args ----------------
parser = argparse.ArgumentParser()
parser.add_argument("log", help="DataFlash log .bin")
parser.add_argument(
    "--target-speed",
    type=float,
    default=None,
    help="Target cruise speed (m/s)",
)
args = parser.parse_args()


# ---------------- load log ----------------
mlog = mavutil.mavlink_connection(args.log)

att, imu, ster, gps = [], [], [], []


# ---------------- parse log ----------------
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


if not att or not imu or not ster or not gps:
    raise RuntimeError("ERROR: Thiếu ATT / IMU / STER / GPS")


imu_t = [x[0] for x in imu]
ster_t = [x[0] for x in ster]
gps_t = [x[0] for x in gps]

yaw_rate = []
steer = []
speed = []


# ---------------- time align ----------------
for t, _ in att:
    gz = nearest(t, imu_t, imu)
    st = nearest(t, ster_t, ster)
    sp = nearest(t, gps_t, gps)

    if gz and st and sp:
        yaw_rate.append(gz[1])
        steer.append(st[1] / STEER_NORM)
        speed.append(sp[1])


if len(yaw_rate) < MIN_SAMPLES:
    raise RuntimeError("ERROR: Dữ liệu hợp lệ quá ít")


yaw_rate = normalize(yaw_rate)
steer = normalize(steer)
speed = normalize(speed)

mask = np.abs(steer) > 0.25
yaw_rate = yaw_rate[mask]
steer = steer[mask]
speed = speed[mask]


# ---------------- metrics ----------------
osc = np.std(yaw_rate)
bias = abs(np.mean(yaw_rate))
effort = np.mean(np.abs(steer))
yaw_rate_95 = np.percentile(np.abs(yaw_rate), 95)
speed_log = clamp(np.median(np.abs(speed)), 0.5, 6.0)


# ---------------- base tuning ----------------
ATC_STR_RAT_P = clamp(0.25 / (osc + 1e-3), 0.10, 0.70)
ATC_STR_RAT_D = clamp(osc * 0.12, 0.01, 0.15)
ATC_STR_RAT_I = clamp(bias * 0.02, 0.0, 0.05)

ATC_STR_RAT_FF = clamp(effort * 0.9, 0.10, 0.40)
ATC_STR_RAT_D_FF = clamp(yaw_rate_95 * 0.15, 0.01, 0.20)
ATC_STR_RAT_MAX = clamp(yaw_rate_95 * 57.3 * 1.2, 30, 80)

ATC_SPEED_FF = clamp(0.6 + speed_log * 0.15, 0.6, 1.2)

speed_acc = np.diff(speed)
ATC_SPEED_D_FF = clamp(np.std(speed_acc) * 0.8, 0.0, 0.5)

yaw_accel = np.diff(yaw_rate)
ATC_ACCEL_MAX = clamp(1.8 - np.std(yaw_accel) * 2.0, 0.8, 2.0)


# ---------------- scale to target speed ----------------
CRUISE_SPEED = speed_log

if args.target_speed:
    scale = args.target_speed / speed_log
    CRUISE_SPEED = args.target_speed

    ATC_STR_RAT_P /= scale
    ATC_STR_RAT_I /= scale
    ATC_STR_RAT_D /= scale

    ATC_STR_RAT_FF *= scale
    ATC_STR_RAT_D_FF *= scale
    ATC_STR_RAT_MAX *= scale

    ATC_SPEED_FF *= scale
    ATC_SPEED_D_FF *= scale
    ATC_ACCEL_MAX *= scale


# ---------------- output ----------------
print("\n===== Skid-Steer Rover Autotune (Scaled) =====\n")
print(f"Samples              : {len(yaw_rate)}")
print(f"Cruise speed (m/s)   : {CRUISE_SPEED:.2f}\n")

print("ATC_STR_RAT_P      =", round(ATC_STR_RAT_P, 3))
print("ATC_STR_RAT_I      =", round(ATC_STR_RAT_I, 3))
print("ATC_STR_RAT_D      =", round(ATC_STR_RAT_D, 3))
print("ATC_STR_RAT_FF     =", round(ATC_STR_RAT_FF, 2))
print("ATC_STR_RAT_D_FF   =", round(ATC_STR_RAT_D_FF, 3))
print("ATC_STR_RAT_MAX    =", round(ATC_STR_RAT_MAX, 1))
print("ATC_SPEED_FF       =", round(ATC_SPEED_FF, 2))
print("ATC_SPEED_D_FF     =", round(ATC_SPEED_D_FF, 2))
print("ATC_ACCEL_MAX      =", round(ATC_ACCEL_MAX, 2))
