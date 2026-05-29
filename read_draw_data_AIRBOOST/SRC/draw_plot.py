import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# ====== THÊM: tkinter để chọn file ======
import tkinter as tk
from tkinter import filedialog, messagebox

# ================== CẤU HÌNH ==================
log_dir = "log_src"
output_dir = "plots"
os.makedirs(output_dir, exist_ok=True)


# ================== CHỌN FILE LOG (TKINTER) ==================
def pick_log_file(initial_dir):
    # tạo root ẩn
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    # nếu thư mục không tồn tại thì fallback về thư mục hiện tại
    init_dir = initial_dir if os.path.isdir(initial_dir) else os.getcwd()

    file_path = filedialog.askopenfilename(
        title="Chọn file log để vẽ",
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
print(f"[INFO] Đang xử lý: {latest_file}")
print(f"[INFO] Đường dẫn: {file_path}")

# ================== ĐỌC DỮ LIỆU  ==================
valid_data = []
line_number = 0

with open(file_path, "r", encoding="utf-8") as f:
    for raw_line in f:
        line_number += 1
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(",")]

        # === KIỂM TRA ĐỊNH DẠNG CHUẨN: đúng 11 cột + tất cả là số hợp lệ ===
        if len(parts) != 11:
            print(f"[WARN] Bỏ qua dòng {line_number}: sai số cột ({len(parts)} ≠ 11)")
            continue

        try:
            row = [float(p) for p in parts]
            # Kiểm tra giá trị thời gian tăng dần
            if valid_data and row[0] < valid_data[-1][0]:
                print(
                    f"[WARN] Bỏ qua dòng {line_number}: thời gian giảm (không hợp lệ)"
                )
                continue
            valid_data.append(row)
        except ValueError as e:
            print(f"[WARN] Bỏ qua dòng {line_number}: chứa giá trị không phải số → {e}")

# Chuyển sang numpy
if len(valid_data) < 10:
    print("[ERROR] Dữ liệu hợp lệ quá ít sau khi lọc!")
    raise SystemExit

data = np.array(valid_data)
print(f"[SUCCESS] ĐÃ LỌC XONG: {len(data)} / {line_number} dòng hợp lệ")

# ================== GÁN DỮ LIỆU ==================
t_s = data[:, 0]
x_act = data[:, 1]
y_act = data[:, 2]
yaw_act = data[:, 3]
x_des = data[:, 4]
y_des = data[:, 5]
yaw_des = data[:, 6]
u_z = data[:, 7]
u_yaw = data[:, 8]
motor1 = data[:, 9]
motor2 = data[:, 10]


# ================== TÌM ĐIỂM SETPOINT  ==================
def find_changes(values, threshold):
    idx = [0]
    for i in range(1, len(values)):
        if abs(values[i] - values[i - 1]) > threshold:
            idx.append(i)
    return idx


idx_x = find_changes(x_des, 0.01)
idx_y = find_changes(y_des, 0.01)
idx_yaw = find_changes(yaw_des, 0.5)

# ================== VẼ ĐỒ THỊ – LEGEND ==================
plt.rcParams.update(
    {
        "figure.figsize": (16, 11),
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "lines.linewidth": 2.0,
    }
)

fig = plt.figure()
fig.suptitle(
    f"Kết quả thử nghiệm - FILE: {latest_file}",
    fontsize=18,
    fontweight="bold",
    y=0.955,
)

gs = fig.add_gridspec(5, 2, width_ratios=[20, 1.3], wspace=0.08, hspace=0.5)
axs = [fig.add_subplot(gs[i, 0]) for i in range(5)]

c_act = "#D41119"  # đỏ thực tế
c_des = "#1f77b4"  # xanh mục tiêu

# === VẼ 5 ĐỒ THỊ ===
axs[0].plot(t_s, x_act, color=c_act, linewidth=2.2)
axs[0].plot(t_s, x_des, color=c_des, linestyle="--", linewidth=2.5)
axs[0].plot(
    t_s[idx_x],
    x_des[idx_x],
    "o",
    color=c_des,
    markersize=7,
    markeredgecolor="black",
    markeredgewidth=1.2,
    zorder=5,
)
axs[0].set_ylabel("X (m)")
axs[0].set_title("Vị trí X theo thời gian", fontweight="bold", pad=12)

axs[1].plot(t_s, y_act, color=c_act, linewidth=2.2)
axs[1].plot(t_s, y_des, color=c_des, linestyle="--", linewidth=2.5)
axs[1].plot(
    t_s[idx_y],
    y_des[idx_y],
    "o",
    color=c_des,
    markersize=7,
    markeredgecolor="black",
    markeredgewidth=1.2,
    zorder=5,
)
axs[1].set_ylabel("Y (m)")
axs[1].set_title("Vị trí Y theo thời gian", fontweight="bold", pad=12)

axs[2].plot(t_s, yaw_act, color=c_act, linewidth=2.2)
axs[2].plot(t_s, yaw_des, color=c_des, linestyle="--", linewidth=2.5)
axs[2].plot(
    t_s[idx_yaw],
    yaw_des[idx_yaw],
    "o",
    color=c_des,
    markersize=7,
    markeredgecolor="black",
    markeredgewidth=1.2,
    zorder=5,
)
axs[2].set_ylabel("Yaw (độ)")
axs[2].set_title("Góc quay Yaw theo thời gian", fontweight="bold", pad=12)

axs[3].plot(t_s, u_z, color="#1EE979", linewidth=2.2)
axs[3].plot(t_s, u_yaw, color="#9C27B0", linewidth=2.2)
axs[3].set_ylabel("Giá trị điều khiển")
axs[3].set_title("Tín hiệu điều khiển", fontweight="bold", pad=12)

axs[4].plot(t_s, motor1, color="#FF5722", linewidth=2.2)
axs[4].plot(t_s, motor2, color="#3F51B5", linewidth=2.2)
axs[4].set_xlabel("Thời gian (giây)", fontweight="bold", fontsize=13)
axs[4].set_ylabel("Tốc độ (RPM)")
axs[4].set_title("Tốc độ động cơ", fontweight="bold", pad=12)

for ax in axs:
    ax.set_xlim(t_s[0], t_s[-1])

# ================== LEGEND CHUNG BÊN PHẢI ==================
legend_ax = fig.add_subplot(gs[:, 1])
legend_ax.axis("off")

legend_elements = [
    Line2D([0], [0], color=c_act, lw=2.5, label="Thực tế"),
    Line2D([0], [0], color=c_des, linestyle="--", lw=2.5, label="Mục tiêu"),
    Line2D(
        [0],
        [0],
        marker="o",
        color="w",
        markerfacecolor=c_des,
        markeredgecolor="k",
        markersize=8,
        label="Setpoint",
    ),
    Line2D([0], [0], color="#1EE979", lw=2.5, label="u_z (lực đẩy)"),
    Line2D([0], [0], color="#9C27B0", lw=2.5, label="u_yaw (lực xoay)"),
    Line2D([0], [0], color="#FF5722", lw=2.5, label="Motor 1"),
    Line2D([0], [0], color="#3F51B5", lw=2.5, label="Motor 2"),
]

legend_ax.legend(
    handles=legend_elements,
    loc="center left",
    fontsize=12.5,
    frameon=True,
    fancybox=True,
    shadow=True,
    borderpad=0.8,
    labelspacing=1.1,
    handletextpad=0.8,
)

# ================== LƯU FILE ==================
final_name = os.path.splitext(latest_file)[0]
output_filename = f"Plot_{final_name}.png"
save_path = os.path.join(output_dir, output_filename)
fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white")
print(f"[SUCCESS] Đã lưu đồ thị tại: {save_path}")

plt.show()
