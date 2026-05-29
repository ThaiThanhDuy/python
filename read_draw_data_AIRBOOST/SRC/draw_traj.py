import os
import math
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

# ====== THÊM: tkinter để chọn file ======
import tkinter as tk
from tkinter import filedialog

# ================== CẤU HÌNH ==================
log_dir = "log_src"
output_dir = "Traj_XY"

# Chỉ số cột (0-based)
IDX_X_ACT = 1
IDX_Y_ACT = 2
IDX_YAW_DEG = 3  # ← Góc yaw (độ) - dùng để vẽ mũi tên
IDX_X_DES = 4
IDX_Y_DES = 5

MAX_JUMP_DISTANCE = 10.0
os.makedirs(output_dir, exist_ok=True)


# ================== CHỌN FILE LOG (TKINTER) ==================
def pick_log_file(initial_dir):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    init_dir = initial_dir if os.path.isdir(initial_dir) else os.getcwd()

    file_path = filedialog.askopenfilename(
        title="Chọn file log để vẽ quỹ đạo XY",
        initialdir=init_dir,
        filetypes=[
            ("Log files (*.txt, *.csv)", "*.txt *.csv"),
            ("Text files (*.txt)", "*.txt"),
            ("CSV files (*.csv)", "*.csv"),
            ("All files (*.*)", "*.*"),
        ],
    )

    root.destroy()
    return file_path


file_path = pick_log_file(log_dir)
if not file_path:
    print("[INFO] Bạn đã huỷ chọn file. Thoát chương trình.")
    raise SystemExit

latest_file = os.path.basename(file_path)
print(f"Đang xử lý: {latest_file}")
print(f"Đường dẫn: {file_path}")

# ================== ĐỌC DỮ LIỆU ==================
x_act, y_act, yaw_deg = [], [], []
x_des, y_des = [], []

last_x = last_y = None

with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) != 11:
            continue
        try:
            vals = [float(p.strip()) for p in parts]
            if any(math.isnan(v) or math.isinf(v) for v in vals):
                continue
        except:
            continue

        x_a = vals[IDX_X_ACT]
        y_a = vals[IDX_Y_ACT]
        yaw = vals[IDX_YAW_DEG]
        x_d, y_d = vals[IDX_X_DES], vals[IDX_Y_DES]

        # Lọc spike
        if (
            last_x is not None
            and math.hypot(x_a - last_x, y_a - last_y) > MAX_JUMP_DISTANCE
        ):
            continue

        x_act.append(x_a)
        y_act.append(y_a)
        yaw_deg.append(yaw)
        x_des.append(x_d)
        y_des.append(y_d)
        last_x, last_y = x_a, y_a

if len(x_act) == 0:
    print("Không có dữ liệu hợp lệ!")
    raise SystemExit

print(
    f"Đọc thành công {len(x_act)} điểm → Sẽ vẽ toàn bộ {len(x_act)} mũi tên (nhỏ gọn)"
)

# Chuyển numpy
x_act = np.array(x_act)
y_act = np.array(y_act)
yaw_deg = np.array(yaw_deg)
x_des = np.array(x_des)
y_des = np.array(y_des)

# Làm mượt quỹ đạo thực tế
win = min(51, len(x_act) if len(x_act) % 2 == 1 else len(x_act) - 1)
if win >= 13:
    x_smooth = savgol_filter(x_act, window_length=win, polyorder=3)
    y_smooth = savgol_filter(y_act, window_length=win, polyorder=3)
else:
    x_smooth, y_smooth = x_act.copy(), y_act.copy()

# ================== TÍNH ĐỘ DÀI MŨI TÊN TỰ ĐỘNG (NHỎ & ĐẸP) ==================
dists = np.sqrt(np.diff(x_smooth) ** 2 + np.diff(y_smooth) ** 2)
avg_dist = np.mean(dists) if len(dists) > 0 else 1.0
arrow_length = max(0.08, avg_dist * 0.3)

# ================== VẼ ĐỒ THỊ ==================
plt.figure(figsize=(14, 11))

# 1. Quỹ đạo mong muốn
plt.plot(x_des, y_des, "r--", linewidth=1.5, alpha=0.8, label="Mong muốn")

# 2. Quỹ đạo thực tế
plt.plot(x_smooth, y_smooth, "b-", linewidth=2.2, label="Thực tế")

# 3. VẼ TOÀN BỘ MŨI TÊN NHỎ GỌN
for i in range(len(x_smooth)):
    angle_rad = math.radians(yaw_deg[i])
    dx = arrow_length * math.cos(angle_rad)
    dy = arrow_length * math.sin(angle_rad)

    plt.arrow(
        x_smooth[i],
        y_smooth[i],
        dx,
        dy,
        head_width=arrow_length * 0.5,
        head_length=arrow_length * 0.5,
        fc="darkgreen",
        ec="darkgreen",
        linewidth=0.3,
        length_includes_head=True,
        alpha=0.85,
        zorder=5,
    )

# 4. Start & End
plt.plot(
    x_act[0],
    y_act[0],
    "go",
    markersize=14,
    markeredgecolor="k",
    markeredgewidth=2,
    label="Start",
)
plt.plot(
    x_act[-1],
    y_act[-1],
    "rs",
    markersize=12,
    markeredgecolor="k",
    markeredgewidth=2,
    label="End",
)

# Cấu hình
plt.xlabel("X (m)", fontsize=14)
plt.ylabel("Y (m)", fontsize=14)
plt.title(f"Quỹ Đạo XY + Hướng Xe\n{latest_file}", fontsize=15, pad=20)
plt.legend(fontsize=12, loc="upper right")
plt.grid(True, alpha=0.3)
plt.axis("equal")

# Zoom đẹp
pad = max(1.0, (x_act.max() - x_act.min()) * 0.05)
all_x = np.concatenate([x_act, x_des])
all_y = np.concatenate([y_act, y_des])
plt.xlim(all_x.min() - pad, all_x.max() + pad)
plt.ylim(all_y.min() - pad, all_y.max() + pad)

# ================== LƯU ẢNH VÀO THƯ MỤC Traj_XY ==================
safe_name = os.path.splitext(latest_file)[0]
output_filename = f"Traj_{safe_name}.png"
output_path = os.path.join(output_dir, output_filename)

plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
print(f"ĐÃ LƯU QUỸ ĐẠO VÀO: {output_path}")
plt.show()
