#!/usr/bin/env python3
"""
Hệ thống phân tích dữ liệu ao nuôi: Phân tầng độ kiềm Sáng - Chiều (Phiên bản cải tiến)
- Thêm độ lệch chuẩn (std) và hệ số biến thiên (CV)
- Sử dụng argparse
- Cải thiện logic xử lý thời gian
- Đánh giá thông minh hơn
- Code sạch hơn, dễ bảo trì
"""

import json
import os
import argparse
from datetime import datetime
from typing import Dict, List, Any
import numpy as np

# -------------------------------------------------------------------------
# CẤU HÌNH HỆ THỐNG (Config)
# -------------------------------------------------------------------------
DEFAULT_FILE = "sensor_api_data.jsonl"

# Ngưỡng tiêu chuẩn độ kiềm
LOW_KH_THRESHOLD = 90.0  # mg/L CaCO3
HIGH_VARIATION_THRESHOLD = 30.0  # mg/L chênh lệch sáng-chiều


def is_time_in_range(target_time_str: str, start_str: str, end_str: str) -> bool:
    """Kiểm tra thời gian có nằm trong khoảng không."""
    try:
        target = datetime.strptime(target_time_str, "%H:%M:%S").time()
        start = datetime.strptime(start_str, "%H:%M:%S").time()
        end = datetime.strptime(end_str, "%H:%M:%S").time()
        return start <= target <= end
    except ValueError:
        return False


def calculate_metrics(data_list: List[float], low_alert_count: int) -> Dict[str, float]:
    """Tính toán các chỉ số thống kê nâng cao."""
    if not data_list:
        return {
            "mean": 0.0,
            "max": 0.0,
            "min": 0.0,
            "std": 0.0,
            "low_alert_pct": 0.0,
            "cv": 0.0,
        }

    arr = np.array(data_list)
    mean_val = float(np.mean(arr))

    return {
        "mean": round(mean_val, 2),
        "max": round(float(np.max(arr)), 2),
        "min": round(float(np.min(arr)), 2),
        "std": round(float(np.std(arr)), 2),
        "low_alert_pct": round((low_alert_count / len(data_list)) * 100, 1),
        "cv": round((np.std(arr) / mean_val) * 100, 1) if mean_val > 0 else 0.0,
    }


def analyze_aquaculture_data(file_path: str) -> None:
    """Phân tích dữ liệu độ kiềm theo buổi sáng và chiều."""
    if not os.path.exists(file_path):
        print(f"[LỖI] File '{file_path}' không tồn tại!")
        return

    morning_kh: List[float] = []
    afternoon_kh: List[float] = []

    morning_low_alerts = 0
    afternoon_low_alerts = 0
    total_records = 0
    invalid_records = 0

    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line:
                    continue

                try:
                    record: Dict[str, Any] = json.loads(clean_line)
                    total_records += 1

                    time_str = record["time"]
                    kh_mg = float(record["sensor_data"]["alkalinity_mg_l"])
                    alert_status = record["system_status"]["alkalinity_alert"]

                    if is_time_in_range(time_str, "05:00:00", "11:59:59"):
                        morning_kh.append(kh_mg)
                        if alert_status == "THẤP":
                            morning_low_alerts += 1
                    elif is_time_in_range(time_str, "12:00:00", "18:00:00"):
                        afternoon_kh.append(kh_mg)
                        if alert_status == "THẤP":
                            afternoon_low_alerts += 1

                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    invalid_records += 1
                    continue

    except IOError as e:
        print(f"[LỖI] Không thể đọc file: {e}")
        return

    # Tính toán metrics
    morning_stats = calculate_metrics(morning_kh, morning_low_alerts)
    afternoon_stats = calculate_metrics(afternoon_kh, afternoon_low_alerts)

    # -------------------------------------------------------------------------
    # OUTPUT: BÁO CÁO
    # -------------------------------------------------------------------------
    print("\n" + "=" * 90)
    print(
        f" BÁO CÁO PHÂN TÍCH ĐỘ KIỀM AO NUÔI - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    print("=" * 90)

    print(f"{'Thông số':<38} | {'BUỔI SÁNG':<20} | {'BUỔI CHIỀU':<20}")
    print("-" * 90)
    print(f"{'Khung giờ':<38} | {'05:00-11:59':<20} | {'12:00-18:00':<20}")
    print(f"{'Số mẫu':<38} | {len(morning_kh):<20} | {len(afternoon_kh):<20}")
    print(
        f"{'Độ kiềm Trung bình (mg/L)':<38} | {morning_stats['mean']:<20} | {afternoon_stats['mean']:<20}"
    )
    print(
        f"{'Độ kiềm Cao nhất (mg/L)':<38} | {morning_stats['max']:<20} | {afternoon_stats['max']:<20}"
    )
    print(
        f"{'Độ kiềm Thấp nhất (mg/L)':<38} | {morning_stats['min']:<20} | {afternoon_stats['min']:<20}"
    )
    print(
        f"{'Độ lệch chuẩn (Std)':<38} | {morning_stats['std']:<20} | {afternoon_stats['std']:<20}"
    )
    print(
        f"{'Hệ số biến thiên CV (%)':<38} | {morning_stats['cv']:<20} | {afternoon_stats['cv']:<20}"
    )
    print(
        f"{'Tỷ lệ cảnh báo THẤP (%)':<38} | {morning_stats['low_alert_pct']:<20} | {afternoon_stats['low_alert_pct']:<20}"
    )
    print("=" * 90)

    # ĐÁNH GIÁ CHUYÊN MÔN
    print("\n ĐÁNH GIÁ & KHUYẾN NGHỊ:")
    print("-" * 50)

    if morning_stats["mean"] < LOW_KH_THRESHOLD:
        print(
            f" [!] CẢNH BÁO: Độ kiềm sáng thấp ({morning_stats['mean']} mg/L < {LOW_KH_THRESHOLD})"
        )
        print("     → Nên bổ sung vôi sớm (ban đêm hoặc sáng sớm).")
    else:
        print(f" [+] Độ kiềm buổi sáng ổn định ({morning_stats['mean']} mg/L)")

    diff = afternoon_stats["mean"] - morning_stats["mean"]
    if diff > HIGH_VARIATION_THRESHOLD:
        print(f" [!] CẢNH BÁO: Biến động lớn giữa sáng và chiều ({diff:.1f} mg/L)")
        print("     → Có thể do mật độ tảo cao hoặc quang hợp mạnh.")
    elif diff < -15:
        print(f" [!] Chú ý: Độ kiềm chiều giảm so với sáng ({diff:.1f} mg/L)")

    if morning_stats["cv"] > 25 or afternoon_stats["cv"] > 25:
        print(" [!] Biến động trong ngày khá cao (CV > 25%). Cần theo dõi thêm.")

    if (morning_stats["low_alert_pct"] + afternoon_stats["low_alert_pct"]) / 2 > 30:
        print(
            " [!!] MỨC BÁO ĐỘNG CAO: Tỷ lệ cảnh báo thấp > 30%. Kiểm tra hệ thống khẩn."
        )

    print("=" * 90 + "\n")


# -------------------------------------------------------------------------
# KHỞI CHẠY
# -------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phân tích độ kiềm ao nuôi theo buổi")
    parser.add_argument(
        "--file",
        "-f",
        default=DEFAULT_FILE,
        help="Đường dẫn file JSONL (mặc định: sensor_api_data.jsonl)",
    )
    parser.add_argument(
        "--low-threshold",
        type=float,
        default=LOW_KH_THRESHOLD,
        help="Ngưỡng độ kiềm thấp (mặc định: 90 mg/L)",
    )

    args = parser.parse_args()

    # Cho phép override ngưỡng từ command line
    LOW_KH_THRESHOLD = args.low_threshold

    print(f"Đang phân tích file: {args.file}\n")
    analyze_aquaculture_data(args.file)
