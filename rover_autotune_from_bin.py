#!/usr/bin/env python3
"""
Rover steering PID recommendation tool
Input  : ArduPilot DataFlash .bin
Output : Recommended ATC_STR_RAT_{P,I,D}

Usage:
    python rover_autotune_from_bin.py input.bin
"""

import sys
import numpy as np
from pymavlink import mavutil

# -----------------------------
# Helpers
# -----------------------------
def normalize(x):
    x = np.array(x)
    return x - np.mean(x)

def clamp(v, vmin, vmax):
    return max(vmin, min(v, vmax))


# -----------------------------
# Main
# -----------------------------
if len(sys.argv) != 2:
    print("Usage: python rover_autotune_from_bin.py <log.bin>")
    sys.exit(1)

bin_file = sys.argv[1]

mlog = mavutil.mavlink_connection(bin_file)

t = []
yaw = []
yaw_rate = []
steer = []

# -----------------------------
# Parse log
# -----------------------------
while True:
    msg = mlog.recv_match(blocking=False)
    if msg is None:
        break

    mtype = msg.get_type()

    # Yaw angle
    if mtype == "ATT":
        t.append(msg.TimeUS * 1e-6)
        yaw.append(msg.Yaw)

    # Yaw rate
    elif mtype == "RATE":
        yaw_rate.append(msg.Y)

    # Steering output (đổi servo index nếu cần)
    elif mtype == "SERVO_OUTPUT_RAW":
        steer.append(msg.servo1_raw)

# -----------------------------
# Basic validation
# -----------------------------
n = min(len(yaw), len(yaw_rate), len(steer))
if n < 200:
    print("ERROR: log quá ngắn hoặc thiếu message cần thiết")
    sys.exit(1)

yaw = normalize(yaw[:n])
yaw_rate = normalize(yaw_rate[:n])
steer = normalize(steer[:n])

# scale steering về [-1, 1] xấp xỉ
steer = steer / 500.0

# -----------------------------
# Metrics
# -----------------------------
yaw_rate_std = np.std(yaw_rate)          # rung
yaw_rate_bias = np.mean(yaw_rate)        # lệch lâu dài
steer_effort = np.mean(np.abs(steer))    # độ gắt steering

# -----------------------------
# PID heuristic (giải thích được)
# -----------------------------
# P: nghịch với rung
P = 0.25 / (yaw_rate_std + 1e-3)

# D: tỉ lệ với rung (damping)
D = yaw_rate_std * 0.08

# I: xử lý bias lâu dài
I = abs(yaw_rate_bias) * 0.05

# Clamp theo biên an toàn thực tế Rover
P = clamp(P, 0.05, 0.6)
I = clamp(I, 0.0, 0.15)
D = clamp(D, 0.001, 0.08)

# -----------------------------
# Print result
# -----------------------------
print("\n===== Rover Steering PID Recommendation =====\n")

print("Log metrics:")
print(f"  yaw_rate_std   : {yaw_rate_std:.4f}")
print(f"  yaw_rate_bias  : {yaw_rate_bias:.4f}")
print(f"  steer_effort   : {steer_effort:.4f}\n")

print("Recommended parameters:")
print(f"  ATC_STR_RAT_P  = {P:.3f}")
print(f"  ATC_STR_RAT_I  = {I:.3f}")
print(f"  ATC_STR_RAT_D  = {D:.3f}")

print("\nNotes:")
print("- Áp dụng cho steering rate controller (ArduRover)")
print("- Test lại ở tốc độ tương đương log")
print("- Nếu rung: giảm P hoặc tăng D")
print("- Nếu lệch line lâu dài: tăng I nhẹ")

