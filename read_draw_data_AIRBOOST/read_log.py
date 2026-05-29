from pymavlink import mavutil
import math
import bisect

BIN_FILE = "2026-01-23 16-37-39.bin"
MAX_DT_US = 50_000  # 50 ms

att = []  # (t, yaw)
imu = []  # (t, gyrz)
ster = []  # (t, steer)

mlog = mavutil.mavlink_connection(BIN_FILE)

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

# ---- checks ----
if len(att) == 0 or len(imu) == 0 or len(ster) == 0:
    raise RuntimeError("ERROR: Thiếu ATT / IMU / STER trong log")

imu_t = [x[0] for x in imu]
ster_t = [x[0] for x in ster]

yaw = []
yaw_rate = []
steer = []
time_s = []

t0 = att[0][0]


def nearest(ts, data_t, data_v):
    i = bisect.bisect_left(data_t, ts)
    if i == 0:
        return None
    if i >= len(data_t):
        return None
    before = data_t[i - 1]
    after = data_t[i]
    if abs(after - ts) < abs(ts - before):
        return data_v[i] if abs(after - ts) < MAX_DT_US else None
    else:
        return data_v[i - 1] if abs(ts - before) < MAX_DT_US else None


for t, y in att:
    gyrz = nearest(t, imu_t, imu)
    st = nearest(t, ster_t, ster)

    if gyrz is None or st is None:
        continue

    yaw.append(y)
    yaw_rate.append(gyrz[1])
    steer.append(st[1])
    time_s.append((t - t0) * 1e-6)

if len(yaw) < 200:
    raise RuntimeError(
        f"ERROR: Dữ liệu hợp lệ quá ít\n"
        f"yaw={len(att)}, imu={len(imu)}, ster={len(ster)}, synced={len(yaw)}"
    )

print("OK: Đồng bộ dữ liệu thành công")
print(f"Samples synced: {len(yaw)}")

print(f"Yaw(deg): {min(yaw)*57.3:.1f} .. {max(yaw)*57.3:.1f}")
print(f"YawRate: {min(yaw_rate):.3f} .. {max(yaw_rate):.3f}")
print(f"Steer: {min(steer):.3f} .. {max(steer):.3f}")

# ---- ready for autotune ----
