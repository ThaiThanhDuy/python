#!/usr/bin/env python3
# encoding: utf-8

from pymavlink import mavutil

# Lắng nghe luồng dữ liệu từ SITL (Sử dụng cổng 14551 để tránh tranh chấp với GCS)
master = mavutil.mavlink_connection("udpin:127.0.0.1:14551")

print("Executing: Listening for custom 'PH' telemetry from SITL...")

while True:
    msg = master.recv_match(type="NAMED_VALUE_FLOAT", blocking=True)
    if msg and msg.name == "PH":
        print(
            f"[FIRMWARE DATA] Time: {msg.time_boot_ms}ms | Sensor: {msg.name} | Value: {msg.value:.4f}"
        )
