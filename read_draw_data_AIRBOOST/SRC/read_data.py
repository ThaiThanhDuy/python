import serial
import os
import datetime


def is_port_available(port):
    """Kiểm tra COM port có mở được không"""
    try:
        s = serial.Serial(port)
        s.close()
        return True
    except serial.SerialException:
        return False


def main():
    # -----------------------
    # 0. Tạo thư mục log_src
    # -----------------------
    log_dir = "log_src"
    os.makedirs(log_dir, exist_ok=True)
    print(f"Thư mục log: {log_dir}")

    # -----------------------
    # 1. Kiểm tra COM trước khi mở
    # -----------------------
    com_port = "COM7"
    if not is_port_available(com_port):
        print(f"Lỗi: {com_port} đang bị chiếm hoặc không khả dụng.")
        print("Hãy đóng các chương trình đang dùng COM này và thử lại.")
        return

    # -----------------------
    # 2. Mở cổng COM
    # -----------------------
    ser = serial.Serial(port=com_port, baudrate=115200, timeout=1)
    print(f"Mở {com_port} thành công!")

    # -----------------------
    # 3. Tạo tên file log (có giây)
    # -----------------------
    now = datetime.datetime.now()
    filename = now.strftime("Log_%Y%m%d_%H%M%S.txt")
    filepath = os.path.join(log_dir, filename)
    print(f"Ghi dữ liệu vào file: {filepath}")

    with open(filepath, "w", encoding="utf-8") as file:
        try:
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        print(line)
                        file.write(line + "\n")
                        file.flush()
        except KeyboardInterrupt:
            print("\nDừng ghi log.")
        finally:
            ser.close()
            print("Đã đóng file và cổng COM.")


if __name__ == "__main__":
    main()
