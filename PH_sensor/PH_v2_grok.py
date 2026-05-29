#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi thủy sản: Đo pH, Nhiệt độ và ước lượng kH tức thời.

Tích hợp bộ lọc trung bình trượt pH và phân tầng 3 mức trạng thái kiềm: THẤP, BÌNH THƯỜNG, CAO.
"""

import time
from datetime import datetime
from typing import Tuple
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG TOÀN CỤC (System Configuration)
# -------------------------------------------------------------------------
PORT_NAME = "/dev/ttyUSB0"
# PORT_NAME = "COM22"
SLAVE_ID = 1

# Hệ số hiệu chuẩn cảm biến tầng vật lý
PH_OFFSET = 0.08
TEMP_OFFSET = -27.2

# Cấu hình bộ lọc thời gian ngắn (Moving Average Window)
WINDOW_SIZE = 10
g_ph_history = []  # Hàng đợi lưu trữ trạng thái lịch sử mẫu pH

# Thông số hóa nghiệm hóa chất (Kit Sera)
BASE_ALKALINITY_DKH = 4.0
CONVERSION_FACTOR_DKH = 17.85  # 1 dKH = 17.85 mg/L CaCO3

# -------------------------------------------------------------------------
# KHỞI TẠO GIAO THỨC MODBUS
# -------------------------------------------------------------------------
instrument = minimalmodbus.Instrument(port=PORT_NAME, slaveaddress=SLAVE_ID)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = "N"
instrument.serial.stopbits = 1
instrument.serial.timeout = 1
instrument.mode = minimalmodbus.MODE_RTU


# -------------------------------------------------------------------------
# TẦNG XỬ LÝ TOÁN HỌC (PROCESS STAGE)
# -------------------------------------------------------------------------
def update_and_get_ph_average(new_ph: float, history_list: list, window: int) -> float:
    """Quản lý hàng đợi vòng và tính toán giá trị pH trung bình trượt."""
    history_list.append(new_ph)

    # Kiểm soát biên độ hàng đợi cuốn chiếu (Boundary Control)
    if len(history_list) > window:
        history_list.pop(0)

    return sum(history_list) / len(history_list)


def calculate_estimated_alkalinity(
    ph: float, base_kh: float, temp_c: float
) -> Tuple[float, float]:
    """Ước lượng độ kiềm tức thời dựa trên pH và giá trị kiềm nền (Kit Sera)."""
    if ph < 0.0 or ph > 14.0:
        ph = 8.0  # Chặn lỗi cấu trúc (Fallback Control)

    # Khóa bão hòa kiểm soát biên nhiệt độ đầu vào
    temp_factor = 1.0 - (temp_c - 28.0) * 0.008
    temp_factor = max(0.85, min(1.1, temp_factor))

    # Định hình hệ số đa tầng theo dải pH
    if ph >= 8.3:
        factor = 1.0 + (ph - 8.3) * 0.32
    elif ph <= 7.6:
        factor = 1.0 - (7.6 - ph) * 0.45
    else:
        factor = 1.0 + (ph - 8.0) * 0.15

    # Khóa giới hạn biên an toàn (Boundary Control)
    factor = max(0.55, min(1.75, factor * temp_factor))

    alk_dkh = round(base_kh * factor, 2)
    alk_mg_l = round(alk_dkh * CONVERSION_FACTOR_DKH, 1)

    return alk_dkh, alk_mg_l


def evaluate_alkalinity_status(alk_mg_l: float) -> str:
    """Phân tầng trạng thái độ kiềm theo 3 phân ngưỡng: THẤP, BÌNH THƯỜNG, CAO."""
    if alk_mg_l < 90.0:
        return "THẤP"
    elif alk_mg_l > 180.0:
        return "CAO"
    else:
        return "BÌNH THƯỜNG"


# -------------------------------------------------------------------------
# CHƯƠNG TRÌNH CHÍNH (INPUT -> PROCESS -> OUTPUT)
# -------------------------------------------------------------------------
print(
    f"Khởi động hệ thống lọc trung bình trượt và phân tầng trạng thái trên {PORT_NAME}..."
)
print(f"Cửa sổ lấy mẫu trung bình ngắn: {WINDOW_SIZE} mẫu ({WINDOW_SIZE * 2} giây)")
print("=" * 100)

try:
    while True:
        try:
            current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            # 1. INPUT STAGE: Đọc dữ liệu thô từ hai thanh ghi Modbus độc lập
            raw_ph = instrument.read_register(0, number_of_decimals=2, functioncode=3)
            raw_temp = instrument.read_register(1, number_of_decimals=1, functioncode=3)

            # 2. PROCESS STAGE: Tính toán hiệu chuẩn và lọc nhiễu trượt
            ph_calibrated = round(raw_ph + PH_OFFSET, 2)
            ph_calibrated = max(0.0, min(14.0, ph_calibrated))  # Saturation Control

            temp_calibrated = round(raw_temp + TEMP_OFFSET, 1)

            # Cập nhật trạng thái bộ lọc trượt cho pH
            ph_moving_average = update_and_get_ph_average(
                new_ph=ph_calibrated, history_list=g_ph_history, window=WINDOW_SIZE
            )

            # Tính toán độ kiềm kH dựa trên pH trung bình trượt và nhiệt độ đã khôi phục
            current_kh_dkh, current_kh_mg = calculate_estimated_alkalinity(
                ph=ph_moving_average,
                base_kh=BASE_ALKALINITY_DKH,
                temp_c=temp_calibrated,
            )

            # Đánh giá mức độ an toàn của độ kiềm hiện tại
            alert_status = evaluate_alkalinity_status(current_kh_mg)

            # 3. OUTPUT STAGE: Xuất dữ liệu cấu trúc đồng bộ hệ thống
            print(f"[{current_time}]")
            print(f"   pH Realtime   : {ph_calibrated:.2f}")
            print(
                f"   pH TRUNG BÌNH ({len(g_ph_history)} mẫu): {ph_moving_average:.2f}"
            )
            print(f"   Nhiệt độ      : {temp_calibrated:.1f} °C")
            print(
                f"   Độ kiềm (kH)  : {current_kh_dkh:.2f} dKH | {current_kh_mg:.1f} mg/L CaCO3"
            )
            print(f"   MỨC ĐỘ KIỀM   : {alert_status}")
            print("-" * 100)

        except IOError as e:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI TRUYỀN DẪN] Modbus thất bại: {e}"
            )
        except Exception as e:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI HỆ THỐNG] {e}"
            )

        time.sleep(2.0)  # Chu kỳ trích xuất cố định 2 giây (Sampling Rate = 0.5Hz)

except KeyboardInterrupt:
    print("\n\nHệ thống đã đóng tiến trình giám sát an toàn.")
except Exception as e:
    print(f"\nLỗi nghiêm trọng toàn cục: {e}")
