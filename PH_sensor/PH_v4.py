#!/usr/bin/env python3
"""Hệ thống giám sát ao nuôi thủy sản: Đo pH, Điện áp đầu dò, Nhiệt độ và kH.

Tích hợp hệ thống lưu trữ dữ liệu thời gian thực dạng cấu trúc JSON Lines (.jsonl)
để phục vụ đồng bộ API, quản lý chặt chẽ chu kỳ I/O và Undefined Behavior.
"""

from datetime import datetime
import json
import os
import time
from typing import List, Tuple
import minimalmodbus

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG TOÀN CỤC (System Configuration)
# -------------------------------------------------------------------------
PORT_NAME: str = "/dev/ttyUSB0"
SLAVE_ID: int = 1  # ID mặc định của cảm biến pH Nengshi

# Cấu hình lưu trữ dữ liệu (Data Logging Configuration)
DATA_LOG_FILE: str = "sensor_api_data.jsonl"

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


def write_to_storage_safely(file_path: str, payload: dict) -> None:
    """Thực thi ghi dữ liệu xuống bộ nhớ vật lý an toàn (Fail-safe Storage).

    Quản lý chặt chẽ quy trình I/O nhằm tránh bão hòa file và hư hỏng hệ thống tập tin.
    """
    try:
        # Chuyển đổi dict sang chuỗi json một dòng kèm ký tự xuống dòng
        json_line: str = json.dumps(payload, ensure_ascii=False) + "\n"

        # Mở file ở chế độ append (a+) để ghi nối tiếp dòng
        with open(file_path, mode="a", encoding="utf-8") as file_ptr:
            file_ptr.write(json_line)
            # Ép luồng dữ liệu từ RAM xuống cache đĩa cứng ngay lập tức
            file_ptr.flush()
            # Đồng bộ hóa bộ đệm hệ điều hành với ổ đĩa vật lý (SD Card/SSD)
            os.fsync(file_ptr.fileno())
    except IOError as storage_err:
        print(
            f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] "
            f"[LỖI LƯU TRỮ VẬT LÝ] Không thể ghi dữ liệu xuống file: {storage_err}"
        )


# -------------------------------------------------------------------------
# CHƯƠNG TRÌNH CHÍNH (INPUT -> PROCESS -> OUTPUT)
# -------------------------------------------------------------------------
print(f"Khởi động hệ thống lọc trung bình trượt trên {PORT_NAME}...")
print(f"File lưu trữ dữ liệu API: {os.path.abspath(DATA_LOG_FILE)}")
print("=" * 100)

try:
    while True:
        try:
            # Khởi tạo đối tượng thời gian đồng bộ cho toàn bộ vòng lặp
            now: datetime = datetime.now()
            date_str: str = now.strftime("%Y-%m-%d")
            time_str: str = now.strftime("%H:%M:%S")

            # 1. INPUT STAGE: Đọc khối thanh ghi Modbus
            registers = instrument.read_registers(
                registeraddress=REG_START_ADDRESS,
                number_of_registers=NUM_REGISTERS_TO_READ,
                functioncode=4,
            )

            raw_ph_int: int = registers[0]
            raw_mv_int: int = registers[2]
            raw_temp_int: int = registers[8]

            # 2. PROCESS STAGE: Giải mã và tính toán
            ph_decoded = raw_ph_int / 100.0
            ph_calibrated = round(ph_decoded + PH_OFFSET, 2)
            ph_calibrated = max(0.0, min(14.0, ph_calibrated))

            electrode_mv = parse_signed_16bit(raw_mv_int)

            temp_signed = parse_signed_16bit(raw_temp_int)
            temp_decoded = temp_signed / 10.0
            temp_calibrated = round(temp_decoded + TEMP_OFFSET, 1)

            ph_moving_average = update_and_get_ph_average(
                new_ph=ph_calibrated, history_list=g_ph_history, window=WINDOW_SIZE
            )

            current_kh_dkh, current_kh_mg = calculate_estimated_alkalinity(
                ph=ph_moving_average,
                base_kh=BASE_ALKALINITY_DKH,
                temp_c=temp_calibrated,
            )

            alert_status = evaluate_alkalinity_status(current_kh_mg)

            if abs(electrode_mv) > ZERO_POTENTIAL_THRESHOLD_MV:
                maintenance_status = "NEED_CLEANING"
                maintenance_desc = f"Độ lệch: {electrode_mv} mV -> Cần vệ sinh hóa chất"
            else:
                maintenance_status = "HEALTHY"
                maintenance_desc = "Đầu dò hoạt động tốt (An toàn)"

            # Cấu trúc hóa Payload chuẩn API (API-Ready Schema)
            api_payload = {
                "date": date_str,
                "time": time_str,
                "timestamp": int(now.timestamp()),
                "sensor_data": {
                    "ph_realtime": ph_calibrated,
                    "ph_moving_average": round(ph_moving_average, 2),
                    "electrode_mv": electrode_mv,
                    "temperature_c": temp_calibrated,
                    "alkalinity_dkh": current_kh_dkh,
                    "alkalinity_mg_l": current_kh_mg,
                },
                "system_status": {
                    "alkalinity_alert": alert_status,
                    "probe_maintenance": maintenance_status,
                },
            }

            # Thực thi ghi xuống file lưu trữ vật lý
            write_to_storage_safely(file_path=DATA_LOG_FILE, payload=api_payload)

            # 3. OUTPUT STAGE: Đồng bộ hiển thị console
            print(f"[{date_str} {time_str}] DỮ LIỆU ĐÃ LƯU")
            print(
                f"   pH Realtime / Average      : {ph_calibrated:.2f} / {ph_moving_average:.2f}"
            )
            print(f"   Điện áp điện cực thô       : {electrode_mv} mV")
            print(f"   Nhiệt độ môi trường        : {temp_calibrated:.1f} °C")
            print(
                f"   Độ kiềm định lượng         : {current_kh_dkh:.2f} dKH | {current_kh_mg:.1f} mg/L"
            )
            print(f"   Bảo trì hệ thống (FMEA)    : {maintenance_desc}")
            print("-" * 100)

        except IOError as io_error:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI TRUYỀN DẪN RS485]: {io_error}"
            )
        except Exception as general_error:
            print(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] [LỖI HỆ THỐNG]: {general_error}"
            )

        time.sleep(2.0)

except KeyboardInterrupt:
    print("\n\n[DỪNG HỆ THỐNG] Đã ngắt tiến trình kiểm tra an toàn.")
except Exception as critical_err:
    print(f"\n[LỖI NGHIÊM TRỌNG] Sập hệ thống toàn cục: {critical_err}")
