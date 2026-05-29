#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi: Tích hợp bộ chuyển đổi đơn vị dKH cho Kit Sera.

Tuân thủ nghiêm ngặt quy ước PEP 8 và nguyên tắc kiểm soát bão hòa hệ thống.
"""

import time
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH THAM SỐ VẬN HÀNH
# -------------------------------------------------------------------------
PORT_NAME = "COM16"
SLAVE_ID = 1

# Hệ số hiệu chuẩn sau đối chiếu thực tế
PH_OFFSET = 0.0
TEMP_OFFSET = -22.2

# Hằng số chuyển đổi đơn vị hóa học
CONVERSION_FACTOR_DKH = 17.85

# Chu kỳ thời gian đặt lại bộ nhớ (24 giờ = 86400 giây)
RESET_INTERVAL_SEC = 86400

# Khởi tạo biến trạng thái toàn cục (State Variables)
g_ph_min = 14.0
g_ph_max = 0.0
g_last_reset_time = time.time()

# Khởi tạo kết nối vật lý Modbus RTU
instrument = minimalmodbus.Instrument(port=PORT_NAME, slaveaddress=SLAVE_ID)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = "N"
instrument.serial.stopbits = 1
instrument.serial.timeout = 1
instrument.mode = minimalmodbus.MODE_RTU


def evaluate_alkalinity(ph_delta: float) -> tuple[str, str]:
    """Phân tích động học hệ đệm và trả về ước tính dải theo 2 đơn vị.

    Hiệu chỉnh chống lỗi hiển thị giả khi hệ thống mới khởi động.
    """
    # Nếu hệ thống mới chạy, biên độ delta bằng 0, không xuất dữ liệu ước tính
    if ph_delta == 0.0:
        return (
            "ĐANG TÍCH LŨY DỮ LIỆU CHU KỲ",
            "ĐANG CHỜ BIẾN THIÊN LỚN NHẤT/NHỎ NHẤT",
        )

    if ph_delta > 0.5:
        return (
            "THẤP (< 60 mg/L)",
            f"THẤP (< {60 / CONVERSION_FACTOR_DKH:.1f} dKH) -> Khớp với thực tế nhỏ giọt",
        )

    if 0.2 <= ph_delta <= 0.5:
        return (
            "TỐI ƯU (80 - 120 mg/L)",
            f"TỐI ƯU ({80 / CONVERSION_FACTOR_DKH:.1f} - {120 / CONVERSION_FACTOR_DKH:.1f} dKH)",
        )

    return (
        "CAO (> 150 mg/L)",
        f"CAO (> {150 / CONVERSION_FACTOR_DKH:.1f} dKH)",
    )


print(f"Hệ thống đang chạy. Chế độ đối chiếu đơn vị kH Sera đã kích hoạt...")

try:
    while True:
        current_time = time.time()

        # Đặt lại bộ nhớ lưu trữ cực trị theo chu kỳ
        if current_time - g_last_reset_time >= RESET_INTERVAL_SEC:
            g_ph_min = 14.0
            g_ph_max = 0.0
            g_last_reset_time = current_time

        try:
            # 1. Input Stage
            raw_ph = instrument.read_register(0, number_of_decimals=2, functioncode=3)
            raw_temp = instrument.read_register(1, number_of_decimals=1, functioncode=3)

            # 2. Process Stage
            ph_calibrated = raw_ph + PH_OFFSET
            temp_calibrated = raw_temp + TEMP_OFFSET

            # Chặn bão hòa giới hạn pH
            if ph_calibrated < 0.0:
                ph_calibrated = 0.0
            elif ph_calibrated > 14.0:
                ph_calibrated = 14.0

            # Cập nhật bộ ghi cực trị ngày/đêm
            if ph_calibrated < g_ph_min:
                g_ph_min = ph_calibrated
            if ph_calibrated > g_ph_max:
                g_ph_max = ph_calibrated

            ph_delta = g_ph_max - g_ph_min
            alk_mg, alk_dkh = evaluate_alkalinity(ph_delta)

            # 3. Output Stage
            print("-" * 80)
            print(
                f"[REALTIME] pH: {ph_calibrated:.2f} | Temp: {temp_calibrated:.1f}°C | Delta pH: {ph_delta:.2f}"
            )
            print(f"[ĐỐI CHIẾU TIÊU CHUẨN CODE]  Ước tính độ kiềm: {alk_mg}")
            print(f"[ĐỐI CHIẾU KIT TEST SERA]   Ước tính độ kiềm: {alk_dkh}")

        except IOError:
            print("[LỖI] Mất kết nối vật lý với cảm biến trên cổng COM16.")

        time.sleep(2.0)

except KeyboardInterrupt:
    print("\nĐã dừng hệ thống an toàn.")
