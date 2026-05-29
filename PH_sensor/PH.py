#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi thủy sản: Đo pH, Nhiệt độ và ước tính Độ kiềm.

Tuân thủ nghiêm ngặt quy ước PEP 8 và quản lý quy trình Input -> Process ->
Output.
"""

import time
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH THAM SỐ VẬN HÀNH (System Configuration)
# -------------------------------------------------------------------------
PORT_NAME = "COM16"
SLAVE_ID = 1

# Hệ số hiệu chuẩn sau đối chiếu thực tế (Calibration Offsets)
PH_OFFSET = 0.0
TEMP_OFFSET = -22.2

# Chu kỳ thời gian đặt lại bộ nhớ pH cực đại/cực tiểu (24 giờ = 86400 giây)
RESET_INTERVAL_SEC = 86400

# -------------------------------------------------------------------------
# KHỞI TẠO BIẾN TRẠNG THÁI TOÀN HỆ THỐNG (State Variables)
# -------------------------------------------------------------------------
g_ph_min = 14.0
g_ph_max = 0.0
g_last_reset_time = time.time()

# Khởi tạo kết nối vật lý Modbus RTU qua cổng COM16
instrument = minimalmodbus.Instrument(port=PORT_NAME, slaveaddress=SLAVE_ID)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = "N"
instrument.serial.stopbits = 1
instrument.serial.timeout = 1
instrument.mode = minimalmodbus.MODE_RTU


def estimate_alkalinity_range(ph_delta: float) -> str:
    """Thuật toán phân tích động học hệ đệm Carbonat để ước tính độ kiềm.

    Args:
        ph_delta: Biên độ dao động pH giữa ngày và đêm.

    Returns:
        str: Đánh giá định tính dải độ kiềm kèm giá trị delta pH thực tế.
    """
    # Thêm ký tự 'f' trước chuỗi và định dạng :.2f để giới hạn 2 chữ số thập phân
    if ph_delta > 0.5:
        return f"Độ kiềm THẤP (< 60 mg/L CaCO3) / Delta pH: {ph_delta:.2f}"

    if 0.2 <= ph_delta <= 0.5:
        return f"Độ kiềm TỐI ƯU (80 - 120 mg/L CaCO3) / Delta pH: {ph_delta:.2f}"

    if 0.0 <= ph_delta < 0.2:
        return f"Độ kiềm RẤT CAO (> 150 mg/L CaCO3) / Delta pH: {ph_delta:.2f}"

    return "CHƯA XÁC ĐỊNH (Cần tích lũy đủ dữ liệu ngày/đêm)"


print(f"Hệ thống giám sát thủy sản tối ưu đang vận hành trên cổng {PORT_NAME}...")

try:
    while True:
        current_time = time.time()

        # Tự động đặt lại bộ nhớ lưu trữ sau mỗi 24 giờ (NASA Control Principle)
        if current_time - g_last_reset_time >= RESET_INTERVAL_SEC:
            g_ph_min = 14.0
            g_ph_max = 0.0
            g_last_reset_time = current_time
            print("[SYSTEM LOG] Đã đặt lại bộ nhớ lưu trữ biên độ pH cho chu kỳ mới.")

        try:
            # 1. INPUT STAGE: Đọc dữ liệu từ thanh ghi Modbus cảm biến ASPS3801
            raw_ph = instrument.read_register(0, number_of_decimals=2, functioncode=3)
            raw_temp = instrument.read_register(1, number_of_decimals=1, functioncode=3)

            # 2. PROCESS STAGE: Áp dụng hệ số hiệu chuẩn và kiểm soát bão hòa
            ph_calibrated = raw_ph + PH_OFFSET
            temp_calibrated = raw_temp + TEMP_OFFSET

            # Giới hạn vật lý bắt buộc của thang đo pH
            if ph_calibrated < 0.0:
                ph_calibrated = 0.0
            elif ph_calibrated > 14.0:
                ph_calibrated = 14.0

            # Cập nhật bộ nhớ lưu trữ pH_min và pH_max trong ngày
            if ph_calibrated < g_ph_min:
                g_ph_min = ph_calibrated
            if ph_calibrated > g_ph_max:
                g_ph_max = ph_calibrated

            # Tính toán biên độ dao động pH thực tế
            ph_delta = g_ph_max - g_ph_min
            alkalinity_status = estimate_alkalinity_range(ph_delta)

            # 3. OUTPUT STAGE: Xuất dữ liệu xử lý ra màn hình giám sát
            print("-" * 80)
            print(
                f"[ĐO THỰC TẾ] pH: {ph_calibrated:.2f} | Nhiệt độ: {temp_calibrated:.1f}°C"
            )
            print(
                f"[HỆ ĐỆM AO]  pH Min: {g_ph_min:.2f} | pH Max: {g_ph_max:.2f} | Biên độ ΔpH: {ph_delta:.2f}"
            )
            print(f"[ƯỚC TÍNH]   Độ kiềm ao nuôi: {alkalinity_status}")

        except IOError:
            print("[LỖI VẬT LÝ] Không nhận được phản hồi từ cảm biến RS485 trên COM16.")

        time.sleep(2.0)  # Tần suất lấy mẫu 2 giây/lần chống quá tải driver

except KeyboardInterrupt:
    print("\n[SYSTEM LOG] Đã dừng tiến trình thu thập dữ liệu an toàn.")
