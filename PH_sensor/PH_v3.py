#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi thủy sản: Đo pH, Điện áp đầu dò, Nhiệt độ và kH.

Tích hợp tính năng giám sát điện áp tĩnh (Zero-potential offset) tại thanh ghi 0x0002
để đưa ra cảnh báo yêu cầu vệ sinh đầu dò bằng hóa chất khi vượt ngưỡng an toàn.
Tuân thủ tiêu chuẩn đặt tên PEP 8 và quản lý chặt chẽ Undefined Behavior.
"""

from datetime import datetime
import time
from typing import List, Tuple
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG TOÀN CỤC (System Configuration)
# -------------------------------------------------------------------------
PORT_NAME: str = "/dev/ttyUSB0"
SLAVE_ID: int = 1  # ID mặc định của cảm biến pH Nengshi

# Địa chỉ cấu trúc thanh ghi Modbus (Nengshi Protocol Map)
REG_START_ADDRESS: int = 0x0000
NUM_REGISTERS_TO_READ: int = 9  # Đọc liên tiếp từ 0x0000 đến 0x0008

# Hệ số hiệu chuẩn thực tế (Tầng vật lý)
PH_OFFSET: float = 0.00
TEMP_OFFSET: float = -3.5

# Ngưỡng phân tầng hệ thống
ALK_MIN: float = 90.0
ALK_MAX: float = 180.0
ZERO_POTENTIAL_THRESHOLD_MV: float = 30.0  # Ngưỡng điện áp tĩnh cho phép (±30mV)

# Cấu hình bộ lọc thời gian ngắn (Moving Average Window)
WINDOW_SIZE: int = 10
g_ph_history: List[float] = []  # Hàng đợi lưu trữ trạng thái mẫu pH

# Thông số hóa nghiệm hóa chất (Kit Sera)
BASE_ALKALINITY_DKH: float = 4.0
CONVERSION_FACTOR_DKH: float = 17.85  # 1 dKH = 17.85 mg/L CaCO3

# -------------------------------------------------------------------------
# KHỞI TẠO GIAO THỨC MODBUS (Modbus Initialization)
# -------------------------------------------------------------------------
try:
    instrument = minimalmodbus.Instrument(port=PORT_NAME, slaveaddress=SLAVE_ID)
    instrument.serial.baudrate = 9600
    instrument.serial.bytesize = 8
    instrument.serial.parity = "N"
    instrument.serial.stopbits = 1
    instrument.serial.timeout = 1  # Giới hạn thời gian phản hồi (Latency Control)
    instrument.mode = minimalmodbus.MODE_RTU
except Exception as init_err:
    print(f"[LỖI KHỞI TẠO PHẦN CỨNG] Không thể thiết lập cấu hình cổng: {init_err}")
    raise SystemExit(init_err) from init_err


# -------------------------------------------------------------------------
# TẦNG XỬ LÝ TOÁN HỌC & ĐỘNG LỰC HỌC (Process Stage)
# -------------------------------------------------------------------------
def update_and_get_ph_average(
    new_ph: float, history_list: List[float], window: int
) -> float:
    """Quản lý hàng đợi vòng và tính toán giá trị pH trung bình trượt."""
    history_list.append(new_ph)

    # Kiểm soát biên độ hàng đợi cuốn chiếu (Boundary Control)
    if len(history_list) > window:
        history_list.pop(0)

    if not history_list:
        return 0.0

    return sum(history_list) / len(history_list)


def calculate_estimated_alkalinity(
    ph: float, base_kh: float, temp_c: float
) -> Tuple[float, float]:
    """Ước lượng độ kiềm tức thời dựa trên pH và giá trị kiềm nền."""
    # Chặn lỗi cấu trúc hệ thống (Fallback Control)
    if ph < 0.0 or ph > 14.0:
        ph = 8.0

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
    if alk_mg_l < ALK_MIN:
        return "THẤP"
    if alk_mg_l > ALK_MAX:
        return "CAO"
    return "BÌNH THƯỜNG"


def parse_signed_16bit(raw_value: int) -> int:
    """Chuyển đổi giá trị số nguyên không dấu 16-bit sang số nguyên có dấu (2's Complement)."""
    if raw_value > 32767:
        return raw_value - 65536
    return raw_value


# -------------------------------------------------------------------------
# CHƯƠNG TRÌNH CHÍNH (INPUT -> PROCESS -> OUTPUT)
# -------------------------------------------------------------------------
print(
    f"Khởi động hệ thống lọc trung bình trượt và phân tầng trạng thái trên {PORT_NAME}..."
)
print(f"Phương thức: Đọc khối thanh ghi liên tiếp (0x0000 - 0x0008) | FC=04")
print("=" * 100)

try:
    while True:
        try:
            current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            # 1. INPUT STAGE: Đọc một khối gồm 9 thanh ghi liên tiếp bằng mã hàm FC=04
            # Tiết kiệm thời gian truyền nhận, loại bỏ hoàn toàn độ trễ bất đồng bộ giữa các thanh ghi
            registers = instrument.read_registers(
                registeraddress=REG_START_ADDRESS,
                number_of_registers=NUM_REGISTERS_TO_READ,
                functioncode=4,
            )

            # Lấy dữ liệu thô từ mảng kết quả
            raw_ph_int: int = registers[0]  # Thanh ghi 0x0000
            raw_mv_int: int = registers[2]  # Thanh ghi 0x0002
            raw_temp_int: int = registers[8]  # Thanh ghi 0x0008

            # 2. PROCESS STAGE: Giải mã vật lý và xử lý dữ liệu có dấu (Signed Integer)
            # Giải mã pH (Scale factor: 100)
            ph_decoded = raw_ph_int / 100.0
            ph_calibrated = round(ph_decoded + PH_OFFSET, 2)
            ph_calibrated = max(0.0, min(14.0, ph_calibrated))  # Saturation Control

            # Giải mã Điện áp điện cực mV (Dữ liệu có dấu Signed Int)
            electrode_mv = parse_signed_16bit(raw_mv_int)

            # Giải mã Nhiệt độ môi trường (Dữ liệu có dấu Signed Int, Scale factor: 10)
            temp_signed = parse_signed_16bit(raw_temp_int)
            temp_decoded = temp_signed / 10.0
            temp_calibrated = round(temp_decoded + TEMP_OFFSET, 1)

            # Cập nhật trạng thái bộ lọc cuốn chiếu cho giá trị pH
            ph_moving_average = update_and_get_ph_average(
                new_ph=ph_calibrated, history_list=g_ph_history, window=WINDOW_SIZE
            )

            # Ước lượng động lực học độ kiềm kH
            current_kh_dkh, current_kh_mg = calculate_estimated_alkalinity(
                ph=ph_moving_average,
                base_kh=BASE_ALKALINITY_DKH,
                temp_c=temp_calibrated,
            )

            # Phân tích trạng thái cảnh báo an toàn ao nuôi
            alert_status = evaluate_alkalinity_status(current_kh_mg)

            # Đánh giá trạng thái mỏi và bám bẩn của đầu dò (Predictive Maintenance)
            # Kiểm tra trị tuyệt đối điện áp tĩnh tại môi trường pH chuẩn hoặc sai lệch vận hành
            if abs(electrode_mv) > ZERO_POTENTIAL_THRESHOLD_MV:
                maintenance_status = f"NGUY CƠ BÁM BẨN CAO (Độ lệch: {electrode_mv} mV) -> CẦN VỆ SINH HÓA CHẤT"
            else:
                maintenance_status = "ĐẦU DÒ HOẠT ĐỘNG TỐT (An toàn)"

            # 3. OUTPUT STAGE: Đồng bộ hiển thị hệ thống dữ liệu chu kỳ
            print(f"[{current_time}]")
            print(f"   pH Realtime                : {ph_calibrated:.2f}")
            print(f"   pH Average                 : {ph_moving_average:.2f}")
            print(f"   Điện áp điện cực thô       : {electrode_mv} mV")
            print(f"   Nhiệt độ môi trường        : {temp_calibrated:.1f} °C")
            print(
                f"   Độ kiềm định lượng         : {current_kh_dkh:.2f} dKH | {current_kh_mg:.1f} mg/L CaCO3"
            )
            print(f"   Trạng thái kiềm trong nước : {alert_status}")
            print(f"   Bảo trì hệ thống (FMEA)    : {maintenance_status}")
            print("-" * 100)

        except IOError as io_error:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] "
                f"[LỖI TRUYỀN DẪN RS485] Không thể đọc khối thanh ghi: {io_error}"
            )
        except Exception as general_error:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] "
                f"[LỖI HỆ THỐNG] Phát sinh hành vi không xác định: {general_error}"
            )

        # Định thời lấy mẫu hệ thống (Sampling Rate = 0.5Hz)
        time.sleep(2.0)

except KeyboardInterrupt:
    print("\n\n[DỪNG HỆ THỐNG] Đã ngắt tiến trình kiểm tra an toàn.")
except Exception as critical_err:
    print(f"\n[LỖI NGHIÊM TRỌNG] Sập hệ thống toàn cục: {critical_err}")
