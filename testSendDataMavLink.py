from pymavlink import mavutil
import time
import random

print("Sending...")

master = mavutil.mavlink_connection(
    'udpout:127.0.0.1:14550',
    source_system=1
)

start_time = time.time()

while True:

    mode = random.choice(["low", "neutral", "high"])

    if mode == "low":
        ph_value = random.uniform(4.0, 5.0)
    elif mode == "neutral":
        ph_value = random.uniform(6.0, 7.0)
    else:
        ph_value = random.uniform(8.0, 9.0)

    time_boot_ms = int((time.time() - start_time) * 1000)

    master.mav.named_value_float_send(
        time_boot_ms,
        b'PH',
        ph_value
    )

    print("PH:", round(ph_value, 2), mode)

    time.sleep(1)
