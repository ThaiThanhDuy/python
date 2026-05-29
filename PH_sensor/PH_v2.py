#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi thủy sản: Đo pH, Nhiệt độ và tính toán kH tức thời.

Sử dụng thư viện tối giản minimalmodbus trên cổng COM16 cho Windows.
"""

import time
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG TOÀN CỤC (System Configuration)
# -------------------------------------------------------------------------
PORT_NAME = "COM16"
SLAVE_ID = 1

# Hệ số hiệu chuẩn cảm biến ASPS3801 sau đối chiếu thực tế
PH_OFFSET = 0.0
TEMP_OFFSET = -22.2

# Điểm nền độ kiềm đo thực tế bằng Kit Sera để làm mốc tuyến tính
# Thay đổi số này nếu kết quả nhỏ giọt thực tế của bạn thay đổi
BASE_ALKALINITY_DKH = 4.0

# Hằng số chuyển đổi đơn vị hóa học (1 dKH = 17.85 mg/L CaCO3)
CONVERSION_FACTOR_DKH = 17.85

# -------------------------------------------------------------------------
# KHỞI TẠO PHẦN CỨNG (Hardware Initialization)
# -------------------------------------------------------------------------
instrument = minimalmodbus.Instrument(port=PORT_NAME, slaveaddress=SLAVE_ID)
instrument.serial.baudrate = 9600
instrument.serial.bytesize = 8
instrument.serial.parity = "N"
instrument.serial.stopbits = 1
instrument.serial.timeout = 1
instrument.mode = minimalmodbus.MODE_RTU


def calculate_instant_alkalinity(ph_now: float, base_kh: float) -> tuple[float, float]:
    """Thuật toán hiệu chỉnh động học hệ đệm toán học Carbonat tức thời.

    Tính toán sự dịch chuyển của độ kiềm dựa trên sự biến thiên pH realtime
    quanh trục tối ưu 8.0 của ao nuôi thủy sản.

    Args:
        ph_now: Giá trị pH hiện tại đã hiệu chuẩn.
        base_kh: Giá trị độ kiềm nền (dKH) nhập từ kết quả thực tế.

    Returns:
        tuple[float, float]: Độ kiềm tính theo dKH và mg/L CaCO3.
    """
    # Xử lý ma trận trọng số phi tuyến tính của ion Carbonat theo pH
    if ph_now > 8.3:
        # Tảo quang hợp mạnh, pH tăng, xuất hiện ion CO3(2-), tăng hoạt tính kiềm
        sensitivity_factor = 1.0 + (ph_now - 8.3) * 0.15
    elif ph_now < 7.5:
        # Hệ thống bị axit hóa, ion HCO3(-) bị tiêu hao để trung hòa axit
        sensitivity_factor = 1.0 - (7.5 - ph_now) * 0.20
    else:
        # Dải ổn định sinh học, hệ đệm giữ cân bằng tuyến tính
        sensitivity_factor = 1.0

    # Tính toán giá trị đầu ra (Process Stage)
    alk_dkh = base_kh * sensitivity_factor
    alk_mg_l = alk_dkh * CONVERSION_FACTOR_DKH

    # Khóa bão hòa kiểm soát lỗi (NASA Boundary Control)
    if alk_dkh < 0.0:
        alk_dkh = 0.0
        alk_mg_l = 0.0

    return alk_dkh, alk_mg_l


def evaluate_aquaculture_safety(ph: float, alk_dkh: float) -> str:
    """Đánh giá rủi ro sinh học trực tiếp cho môi trường ao nuôi."""
    if ph < 7.5 or alk_dkh < 3.5:
        return "CẢNH BÁO: Hệ đệm cạn kiệt, nguy cơ sụt pH cấp tính khi trời mưa!"
    if ph > 8.5:
        return "CẢNH BÁO: Độc tính khí độc NH3 tăng mạnh, cần kiểm soát mật độ tảo!"
    return "TRẠNG THÁI: Môi trường an toàn ổn định."


print(f"Khởi động hệ thống realtime trên cổng {PORT_NAME}...")
print(f"Điểm cấu hình nền kH Sera chốt giữ: {BASE_ALKALINITY_DKH} dKH")
print("-" * 80)

try:
    while True:
        try:
            # 1. INPUT STAGE: Đọc thanh ghi Modbus RTU từ cảm biến
            raw_ph = instrument.read_register(0, number_of_decimals=2, functioncode=3)
            raw_temp = instrument.read_register(1, number_of_decimals=1, functioncode=3)

            # 2. PROCESS STAGE: Hiệu chuẩn sai số vật lý và tính toán
            ph_calibrated = raw_ph + PH_OFFSET
            temp_calibrated = raw_temp + TEMP_OFFSET

            # Bộ lọc bão hòa vật lý chống xung nhiễu truyền thông (EMI Filter)
            if ph_calibrated < 0.0:
                ph_calibrated = 0.0
            elif ph_calibrated > 14.0:
                ph_calibrated = 14.0

            # Tính toán độ kiềm tức thời (Thời gian đáp ứng = 2 giây)
            current_kh_dkh, current_kh_mg = calculate_instant_alkalinity(
                ph_now=ph_calibrated, base_kh=BASE_ALKALINITY_DKH
            )

            # Phân tích trạng thái sinh học
            safety_status = evaluate_aquaculture_safety(ph_calibrated, current_kh_dkh)

            # 3. OUTPUT STAGE: Xuất dữ liệu đồng bộ ra màn hình điều khiển
            print(
                f"[ĐO THỰC TẾ] pH: {ph_calibrated:.2f} | "
                f"Nhiệt độ: {temp_calibrated:.1f}°C"
            )
            print(
                f"[ĐỐI CHIẾU]  Độ kiềm: {current_kh_dkh:.1f} dKH (Kit Sera) | "
                f"{current_kh_mg:.1f} mg/L CaCO3"
            )
            print(f"[LOG HỆ THỐNG] {safety_status}")
            print("-" * 80)

        except IOError:
            print(
                "[LỖI VẬT LÝ] Ngắt kết nối đường truyền RS485 trên cổng COM16. Đang quét lại..."
            )

        # Tốc độ lấy mẫu hệ thống cố định (Sampling Rate = 0.5Hz) chống nghẽn driver
        time.sleep(2.0)

except KeyboardInterrupt:
    print("\n[SYSTEM] Đã ngắt tiến trình giám sát an toàn.")
