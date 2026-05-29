#!/usr/bin/env python3
"""
Skid-Steer Rover Autotune (ArduPilot DataFlash .bin)

- AUTO filter via STAT.flightmode if available
- Fallback gracefully if STAT not present
- Correct cruise speed handling
- Allow fixed desired cruise speed
"""

import math
import bisect
import argparse
import numpy as np
from pymavlink import mavutil

# ================= CONFIG =================
MAX_DT_US = 50_000
STEER_NORM = 4000.0
MIN_SAMPLES = 1500

MIN_CRUISE = 0.5
MAX_CRUISE = 8.0

AUTO_MODE_STR = "AUTO"


# ================= UTILS =================
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


def nearest_mode(ts, data_t, data_v):
    i = bisect.bisect_right(data_t, ts) - 1
    if i < 0:
        return None
    return data_v[i]


# ================= ARGS =================
parser = argparse.ArgumentParser()
parser.add_argument("log", help="DataFlash log .bin")
parser.add_argument(
    "--cruise-speed", type=float, default=None, help="Desired cruise speed (m/s)"
)
args = parser.parse_args()

# ================= LOAD LOG =================
mlog = mavutil.mavlink_connection(args.log)

att, imu, ster, gps = [], [], [], []
stat = []

# ================= PARSE LOG =================
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

    elif mtype == "STAT" and hasattr(msg, "flightmode"):
        stat.append((t, msg.flightmode))

# ================= SANITY (CORE ONLY) =================
if not att or not imu or not ster or not gps:
    raise RuntimeError("ERROR: thiếu ATT / IMU / STER / GPS")

has_stat = len(stat) > 0

if not has_stat:
    print("WARNING: STAT.flightmode không có trong log → KHÔNG lọc AUTO mode")

imu_t = [x[0] for x in imu]
ster_t = [x[0] for x in ster]
gps_t = [x[0] for x in gps]

if has_stat:
    stat_t = [x[0] for x in stat]

yaw_rate = []
steer = []
speed_raw = []

# ================= TIME ALIGN =================
for t, _ in att:
    if has_stat:
        fm = nearest_mode(t, stat_t, stat)
        if fm != AUTO_MODE_STR:
            continue

    gz = nearest(t, imu_t, imu)
    st = nearest(t, ster_t, ster)
    sp = nearest(t, gps_t, gps)

    if gz and st and sp:
        yaw_rate.append(gz[1])
        steer.append(st[1] / STEER_NORM)
        speed_raw.append(sp[1])

yaw_rate = np.asarray(yaw_rate)
steer = np.asarray(steer)
speed_raw = np.asarray(speed_raw)

if len(yaw_rate) < MIN_SAMPLES:
    raise RuntimeError(f"ERROR: không đủ mẫu để autotune (samples={len(yaw_rate)})")

# ================= PREPROCESS =================
yaw_dyn = normalize(yaw_rate)
steer_dyn = normalize(steer)
speed_dyn = normalize(speed_raw)

mask = np.abs(steer_dyn) > 0.25
yaw_dyn = yaw_dyn[mask]
steer_dyn = steer_dyn[mask]
speed_dyn = speed_dyn[mask]
speed_used = speed_raw[mask]

# ================= METRICS =================
osc = np.std(yaw_dyn)
bias = abs(np.mean(yaw_dyn))
effort = np.mean(np.abs(steer_dyn))
yaw95 = np.percentile(np.abs(yaw_dyn), 95)

# ================= CRUISE SPEED =================
speed_log = clamp(np.median(speed_used), MIN_CRUISE, MAX_CRUISE)

CRUISE_DES = args.cruise_speed if args.cruise_speed else speed_log
CRUISE_DES = clamp(CRUISE_DES, MIN_CRUISE, MAX_CRUISE)

scale = CRUISE_DES / speed_log

# ================= TUNING LAWS =================
ATC_STR_RAT_P = clamp((0.25 / (osc + 1e-3)) / scale, 0.10, 0.70)
ATC_STR_RAT_I = clamp((bias * 0.02) / scale, 0.0, 0.05)
ATC_STR_RAT_D = clamp((osc * 0.12) / scale, 0.01, 0.15)

ATC_STR_RAT_FF = clamp(effort * 0.9 * scale, 0.10, 0.40)
ATC_STR_RAT_D_FF = clamp(yaw95 * 0.15 * scale, 0.01, 0.20)
ATC_STR_RAT_MAX = clamp(yaw95 * 57.3 * 1.2 * scale, 30, 90)

ATC_SPEED_FF = clamp(0.6 + CRUISE_DES * 0.15, 0.6, 1.3)

speed_acc = np.diff(speed_dyn)
ATC_SPEED_D_FF = clamp(np.std(speed_acc) * 0.8, 0.0, 0.6)

yaw_acc = np.diff(yaw_dyn)
ATC_ACCEL_MAX = clamp(1.8 - np.std(yaw_acc) * 2.0, 0.8, 2.2)

# ================= OUTPUT =================
print("\n===== Skid-Steer Rover AUTOTUNE =====\n")
print(f"Samples used        : {len(yaw_dyn)}")
print(f"Measured speed (m/s): {speed_log:.2f}")
print(f"Cruise desired (m/s): {CRUISE_DES:.2f}")
print(f"AUTO filtered       : {'YES' if has_stat else 'NO'}\n")

print("ATC_STR_RAT_P    =", round(ATC_STR_RAT_P, 3))
print("ATC_STR_RAT_I    =", round(ATC_STR_RAT_I, 3))
print("ATC_STR_RAT_D    =", round(ATC_STR_RAT_D, 3))
print("ATC_STR_RAT_FF   =", round(ATC_STR_RAT_FF, 2))
print("ATC_STR_RAT_D_FF =", round(ATC_STR_RAT_D_FF, 3))
print("ATC_STR_RAT_MAX  =", round(ATC_STR_RAT_MAX, 1))
print("ATC_SPEED_FF     =", round(ATC_SPEED_FF, 2))
print("ATC_SPEED_D_FF   =", round(ATC_SPEED_D_FF, 2))
print("ATC_ACCEL_MAX    =", round(ATC_ACCEL_MAX, 2))
