import socket
import time
import threading

# Cấu hình kết nối TCP
# Thay đổi bằng địa chỉ IP thực của STM32 của bạn
STM32_IP = "192.168.1.200"
CMD_VEL_PORT = 1100
SENSOR_DATA_SERVER_PORT = 1200  # Cổng mới cho server gửi dữ liệu trên STM32


# --- Chức năng gửi lệnh cmd_vel (không thay đổi) ---
def send_cmd_vel(linear_x, angular_z):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((STM32_IP, CMD_VEL_PORT))
            command_str = f"CMDVEL:{linear_x:.2f},{angular_z:.2f}\r\n"
            print(f"Gửi CMD_VEL: {command_str.strip()}")
            s.sendall(command_str.encode("utf-8"))

            response = s.recv(1024).decode("utf-8").strip()
            print(f"Phản hồi CMD_VEL: {response}")
            return True if "CMDVEL_OK" in response else False
    except Exception as e:
        print(f"Lỗi khi gửi CMD_VEL: {e}")
        return False


# --- Chức năng nhận dữ liệu IMU/Encoder từ STM32 Server ---
def listen_for_sensor_data():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(
                f"Đang kết nối đến STM32 Server tại {STM32_IP}:{SENSOR_DATA_SERVER_PORT} để nhận dữ liệu cảm biến..."
            )
            s.connect((STM32_IP, SENSOR_DATA_SERVER_PORT))
            print("Đã kết nối thành công! Đang chờ dữ liệu...")

            while True:  # Vòng lặp liên tục để nhận dữ liệu
                data = s.recv(1024).decode("utf-8").strip()
                if not data:  # Nếu không nhận được dữ liệu, server đã đóng kết nối
                    print("STM32 Server đã đóng kết nối.")
                    break

                print(f"Nhận được dữ liệu cảm biến: {data}")

                # Phân tích dữ liệu (tùy chọn)
                if "YPR:" in data and "ENC:" in data and "TS:" in data:
                    try:
                        parts = data.split(";")
                        ypr_part = parts[0].replace("YPR:", "").split(",")
                        enc_part = parts[1].replace("ENC:", "").split(",")
                        ts_part = parts[2].replace("TS:", "")

                        ypr_data = {
                            "yaw": float(ypr_part[0]),
                            "pitch": float(ypr_part[1]),
                            "roll": float(ypr_part[2]),
                        }
                        encoder_data = {
                            "left": int(enc_part[0]),
                            "right": int(enc_part[1]),
                        }
                        timestamp = int(ts_part)

                        print(f"  YPR: {ypr_data}")
                        print(f"  Encoder: {encoder_data}")
                        print(f"  Timestamp: {timestamp}")
                    except Exception as parse_e:
                        print(f"Lỗi khi phân tích dữ liệu cảm biến: {parse_e}")

    except Exception as e:
        print(f"Lỗi khi lắng nghe dữ liệu cảm biến: {e}")


# --- Luồng chính để kiểm tra ---
if __name__ == "__main__":
    print("Bắt đầu kiểm tra TCP với STM32...")

    time.sleep(2)  # Đợi STM32 khởi động hoàn toàn

    # Chạy tác vụ lắng nghe dữ liệu cảm biến trong một luồng riêng
    # vì nó sẽ chạy liên tục
    sensor_listener_thread = threading.Thread(target=listen_for_sensor_data)
    sensor_listener_thread.daemon = (
        True  # Đặt là daemon để nó tự kết thúc khi chương trình chính kết thúc
    )
    sensor_listener_thread.start()

    # Chạy các trường hợp kiểm tra gửi CMD_VEL trong luồng chính
    test_cases = [
        {"linear": 0.5, "angular": 0.0},
        {"linear": 0.0, "angular": 1.0},
        {"linear": -0.2, "angular": -0.5},
        {"linear": 0.0, "angular": 0.0},  # Dừng
    ]

    for i, cmd in enumerate(test_cases):
        print(f"\n--- Chu trình CMD_VEL {i+1} ---")
        send_cmd_vel(cmd["linear"], cmd["angular"])
        time.sleep(1)  # Tạm dừng giữa các lệnh CMD_VEL

    print(
        "\nKiểm tra CMD_VEL hoàn tất. Lắng nghe dữ liệu cảm biến sẽ tiếp tục cho đến khi bạn dừng script."
    )

    # Giữ luồng chính chạy để luồng lắng nghe sensor có thể tiếp tục
    # Bạn có thể thêm một vòng lặp vô hạn hoặc input() để giữ nó
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nĐã dừng script.")
