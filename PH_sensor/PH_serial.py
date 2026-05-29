#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi: Đọc Serial thô kiểm soát phản hồi luồng.

Sử dụng cơ chế kiểm tra out_waiting vật lý để chống mất byte CRC.
"""

import time
from datetime import datetime
import serial

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG
# -------------------------------------------------------------------------
PORT_NAME = "COM33"
BAUD_RATE = 9600

PH_OFFSET = 0.0
TEMP_OFFSET = -22.2
BASE_ALKALINITY_DKH = 4.0
CONVERSION_FACTOR_DKH = 17.85

# KHỞI TẠO CỔNG SERIAL VẬT LÝ
ser = serial.Serial(
    port=PORT_NAME,
    baudrate=BAUD_RATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0.1,  # Giảm tối đa timeout đọc byte đơn để tăng tốc độ quét vòng lặp
)


def calculate_estimated_alkalinity(
    ph: float, base_kh: float, temp_c: float
) -> tuple[float, float]:
    """Ước lượng độ kiềm tức thời dựa trên pH và giá trị kiềm nền (Kit Sera)."""
    if ph < 0.0 or ph > 14.0:
        ph = 8.0

    temp_factor = 1.0 - (temp_c - 28.0) * 0.008
    temp_factor = max(0.85, min(1.1, temp_factor))

    if ph >= 8.3:
        factor = 1.0 + (ph - 8.3) * 0.32
    elif ph <= 7.6:
        factor = 1.0 - (7.6 - ph) * 0.45
    else:
        factor = 1.0 + (ph - 8.0) * 0.15

    factor = max(0.55, min(1.75, factor * temp_factor))
    alk_dkh = round(base_kh * factor, 2)
    alk_mg_l = round(alk_dkh * CONVERSION_FACTOR_DKH, 1)

    return alk_dkh, alk_mg_l


print(f"Khởi động bộ dò quét trạng thái bộ đệm trên cổng {PORT_NAME}...")
print("=" * 100)

try:
    while True:
        try:
            current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            # Xóa bộ đệm chống tích tụ dữ liệu rác
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # --- TIẾN TRÌNH PHÁT KIỂM SOÁT PHẢN HỒI (HARDWARE FLOW CONTROL) ---
            ser.setRTS(True)  # Mở mạch phát MAX485

            request_command = b"\x01\x03\x00\x00\x00\x02\xc4\x0b"
            ser.write(request_command)

            # Vòng lặp khóa cứng: Chờ cho đến khi toàn bộ dữ liệu rời khỏi bộ đệm phần cứng của chip
            while ser.out_waiting > 0:
                pass

            # Bổ sung một khoảng bù dịch pha cực nhỏ cho IC MAX485 ổn định đường truyền
            time.sleep(0.005)

            ser.setRTS(False)  # Chuyển sang mạch nhận (RX)
            # -----------------------------------------------------------------

            # --- TIẾN TRÌNH NHẬN ĐỘNG (DYNAMIC RX STAGE) ---
            response_bytes = b""
            start_wait = time.time()

            # Quét liên tục trong 2.0 giây để gom đủ ít nhất 9 bytes
            while (time.time() - start_wait) < 2.0:
                if ser.in_waiting > 0:
                    response_bytes += ser.read(ser.in_waiting)
                if len(response_bytes) >= 9:
                    break
                time.sleep(0.002)

            if len(response_bytes) < 9:
                print(
                    f"[{current_time}] [CẢNH BÁO VẬT LÝ] Gom dữ liệu không đủ chu kỳ (Thu được: {len(response_bytes)}/9 Bytes)."
                )
                time.sleep(2.0)
                continue

            response_bytes = response_bytes[:9]

            # Xác thực cấu trúc gói tin
            if response_bytes[0] != 0x01 or response_bytes[1] != 0x03:
                raise ValueError(
                    "Gói tin bị lệch Byte tiêu đề do sai lệch thời gian chuyển mạch."
                )

            # TẦNG XỬ LÝ TOÁN HỌC (PROCESS STAGE)
            raw_ph_value = (response_bytes[3] << 8) | response_bytes[4]
            raw_temp_value = (response_bytes[5] << 8) | response_bytes[6]

            ph_real = raw_ph_value / 100.0
            temp_real = raw_temp_value / 10.0

            # Áp dụng hiệu chuẩn
            ph_calibrated = round(ph_real + PH_OFFSET, 2)
            temp_calibrated = round(temp_real + TEMP_OFFSET, 1)

            ph_calibrated = max(0.0, min(14.0, ph_calibrated))

            # Tính độ kiềm
            current_kh_dkh, current_kh_mg = calculate_estimated_alkalinity(
                ph=ph_calibrated, base_kh=BASE_ALKALINITY_DKH, temp_c=temp_calibrated
            )

            # TẦNG ĐẦU RA (OUTPUT STAGE)
            print(f"[{current_time}]")
            print(f"   pH          : {ph_calibrated:.2f}")
            print(f"   Nhiệt độ    : {temp_calibrated:.1f} °C")
            print(
                f"   Độ kiềm     : {current_kh_dkh:.2f} dKH | {current_kh_mg:.1f} mg/L CaCO3"
            )
            print("-" * 100)

        except (serial.SerialException, ValueError) as e:
            ser.setRTS(False)
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI TRUYỀN DẪN] {e}"
            )
        except Exception as e:
            ser.setRTS(False)
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI HỆ THỐNG] {e}"
            )

        time.sleep(2.0)

except KeyboardInterrupt:
    print("\n\nHệ thống đã đóng cổng UART an toàn.")
    if ser.is_open:
        ser.close()
