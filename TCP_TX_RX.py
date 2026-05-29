import socket
import time
import threading
import json  # Có thể dùng để log dữ liệu nhận được nếu muốn

# --- Cấu hình kết nối TCP ---
# Thay đổi bằng địa chỉ IP thực của STM32 của bạn
STM32_IP = "192.168.1.200"
CMD_VEL_PORT = 1100  # Cổng cho server nhận lệnh VEL trên STM32
SENSOR_DATA_PORT = 1100  # Cổng cho server gửi dữ liệu cảm biến trên STM32


# --- Cấu trúc dữ liệu nhận được (nếu cần xử lý thêm) ---
# Tùy thuộc vào định dạng bạn gửi từ STM32
class SensorData:
    def __init__(
        self, yaw=0.0, pitch=0.0, roll=0.0, enc_left=0, enc_right=0, timestamp=0
    ):
        self.yaw = yaw
        self.pitch = pitch
        self.roll = roll
        self.enc_left = enc_left
        self.enc_right = enc_right
        self.timestamp = timestamp

    def __str__(self):
        return (
            f"YPR:({self.yaw:.2f}, {self.pitch:.2f}, {self.roll:.2f}), "
            f"ENC:({self.enc_left}, {self.enc_right}), TS:{self.timestamp}"
        )


# --- Biến toàn cục để lưu trữ dữ liệu cảm biến mới nhất ---
latest_sensor_data = SensorData()
data_lock = threading.Lock()  # Mutex để bảo vệ dữ liệu khi truy cập từ nhiều luồng


# --- Luồng gửi lệnh VEL và nhận ACK ---
def send_vel_commands_thread():
    """
    Kết nối tới STM32 trên cổng CMD_VEL_PORT, gửi lệnh VEL và chờ ACK.
    """
    print(f"[CMD_SENDER] Bắt đầu luồng gửi lệnh VEL tới {STM32_IP}:{CMD_VEL_PORT}")
    try:
        # Sử dụng loop để cố gắng kết nối lại nếu bị ngắt
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((STM32_IP, CMD_VEL_PORT))
                    print(f"[CMD_SENDER] Đã kết nối tới {STM32_IP}:{CMD_VEL_PORT}")

                    test_commands = [
                        {"linear": 0.5, "angular": 0.0},
                        {"linear": 0.0, "angular": 1.0},
                        {"linear": -0.2, "angular": -0.5},
                        {"linear": 0.0, "angular": 0.0},  # Dừng
                        {"linear": 0.3, "angular": 0.2},
                    ]

                    for i, cmd in enumerate(test_commands):
                        command_str = (
                            f"VEL:{cmd['linear']:.2f},{cmd['angular']:.2f}\r\n"
                        )
                        print(f"[CMD_SENDER] Gửi: {command_str.strip()}")
                        s.sendall(command_str.encode("utf-8"))

                        response = s.recv(1024).decode("utf-8").strip()
                        print(f"[CMD_SENDER] Nhận ACK: {response}")
                        time.sleep(1)  # Chờ 1 giây trước lệnh tiếp theo

                print(
                    "[CMD_SENDER] Đã gửi hết lệnh, đóng kết nối. Sẽ thử kết nối lại sau 5s."
                )
                time.sleep(5)  # Đợi trước khi thử kết nối lại và gửi lại chuỗi lệnh

            except ConnectionRefusedError:
                print(
                    f"[CMD_SENDER] Kết nối bị từ chối tới {STM32_IP}:{CMD_VEL_PORT}. Đảm bảo STM32 đang chạy server. Thử lại sau 2s."
                )
            except socket.timeout:
                print(
                    f"[CMD_SENDER] Timeout khi kết nối hoặc nhận dữ liệu. Thử lại sau 2s."
                )
            except Exception as e:
                print(f"[CMD_SENDER] Lỗi kết nối hoặc giao tiếp: {e}. Thử lại sau 2s.")

            time.sleep(2)  # Đợi trước khi thử kết nối lại
    except KeyboardInterrupt:
        print("\n[CMD_SENDER] Luồng gửi lệnh VEL đã dừng.")


# --- Luồng nhận dữ liệu cảm biến ---
def receive_sensor_data_thread():
    """
    Kết nối tới STM32 trên cổng SENSOR_DATA_PORT và liên tục nhận dữ liệu cảm biến.
    """
    print(
        f"[SENSOR_RECEIVER] Bắt đầu luồng nhận dữ liệu cảm biến từ {STM32_IP}:{SENSOR_DATA_PORT}"
    )
    global latest_sensor_data  # Khai báo để có thể sửa đổi biến toàn cục

    try:
        # Sử dụng loop để cố gắng kết nối lại nếu bị ngắt
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((STM32_IP, SENSOR_DATA_PORT))
                    print(
                        f"[SENSOR_RECEIVER] Đã kết nối tới {STM32_IP}:{SENSOR_DATA_PORT}. Đang chờ dữ liệu..."
                    )

                    while True:  # Vòng lặp liên tục để nhận dữ liệu từ cùng một kết nối
                        data = s.recv(1024).decode("utf-8").strip()
                        if not data:  # Server đã đóng kết nối
                            print(
                                "[SENSOR_RECEIVER] STM32 Server đã đóng kết nối. Đang thử kết nối lại..."
                            )
                            break  # Thoát vòng lặp nhận dữ liệu để thử kết nối lại

                        # print(f"[SENSOR_RECEIVER] Nhận được dữ liệu thô: {data}") # Bỏ comment để debug

                        # Phân tích cú pháp dữ liệu nhận được
                        parsed_data = parse_sensor_data(data)
                        if parsed_data:
                            with data_lock:  # Bảo vệ truy cập biến toàn cục
                                latest_sensor_data.yaw = parsed_data.yaw
                                latest_sensor_data.pitch = parsed_data.pitch
                                latest_sensor_data.roll = parsed_data.roll
                                latest_sensor_data.enc_left = parsed_data.enc_left
                                latest_sensor_data.enc_right = parsed_data.enc_right
                                latest_sensor_data.timestamp = parsed_data.timestamp
                            # print(f"[SENSOR_RECEIVER] Đã cập nhật dữ liệu: {latest_sensor_data}")
                            # Bạn có thể xử lý dữ liệu ở đây hoặc để một luồng khác đọc latest_sensor_data
                        else:
                            print(
                                f"[SENSOR_RECEIVER] Không thể phân tích dữ liệu: {data}"
                            )

            except ConnectionRefusedError:
                print(
                    f"[SENSOR_RECEIVER] Kết nối bị từ chối tới {STM32_IP}:{SENSOR_DATA_PORT}. Đảm bảo STM32 đang chạy server. Thử lại sau 2s."
                )
            except socket.timeout:
                print(
                    f"[SENSOR_RECEIVER] Timeout khi kết nối hoặc nhận dữ liệu. Thử lại sau 2s."
                )
            except Exception as e:
                print(
                    f"[SENSOR_RECEIVER] Lỗi kết nối hoặc giao tiếp: {e}. Thử lại sau 2s."
                )

            time.sleep(2)  # Đợi trước khi thử kết nối lại
    except KeyboardInterrupt:
        print("\n[SENSOR_RECEIVER] Luồng nhận dữ liệu cảm biến đã dừng.")


# --- Hàm phân tích cú pháp dữ liệu cảm biến ---
def parse_sensor_data(data_str):
    """
    Phân tích chuỗi dữ liệu cảm biến thành đối tượng SensorData.
    Định dạng: YPR:yaw,pitch,roll;ENC:left,right;TS:timestamp
    """
    try:
        parts = data_str.split(";")
        if len(parts) < 3:
            return None  # Không đủ phần

        ypr_part = parts[0]
        enc_part = parts[1]
        ts_part = parts[2]

        # Phân tích YPR
        if ypr_part.startswith("YPR:"):
            ypr_values = [float(v) for v in ypr_part[4:].split(",")]
            yaw, pitch, roll = ypr_values
        else:
            return None

        # Phân tích ENC
        if enc_part.startswith("ENC:"):
            enc_values = [int(v) for v in enc_part[4:].split(",")]
            enc_left, enc_right = enc_values
        else:
            return None

        # Phân tích TS
        if ts_part.startswith("TS:"):
            timestamp = int(ts_part[3:])
        else:
            return None

        return SensorData(yaw, pitch, roll, enc_left, enc_right, timestamp)
    except Exception as e:
        # print(f"Lỗi phân tích dữ liệu: {data_str} -> {e}")
        return None


# --- Luồng chính để khởi tạo và chạy các luồng con ---
if __name__ == "__main__":
    print("Bắt đầu ứng dụng giao tiếp TCP với STM32...")
    print(f"Cấu hình STM32 IP: {STM32_IP}")
    print(f"Cổng gửi lệnh (RX Server trên STM32): {CMD_VEL_PORT}")
    print(f"Cổng nhận dữ liệu (TX Server trên STM32): {SENSOR_DATA_PORT}")

    # Đợi một chút để STM32 khởi động hoàn toàn LwIP và các server
    time.sleep(3)

    # Khởi tạo và chạy luồng gửi lệnh
    cmd_sender_thread = threading.Thread(target=send_vel_commands_thread)
    cmd_sender_thread.daemon = (
        True  # Đặt là daemon để nó tự kết thúc khi chương trình chính kết thúc
    )
    cmd_sender_thread.start()

    # Khởi tạo và chạy luồng nhận dữ liệu cảm biến
    sensor_receiver_thread = threading.Thread(target=receive_sensor_data_thread)
    sensor_receiver_thread.daemon = True
    sensor_receiver_thread.start()

    # --- Ví dụ về cách truy cập dữ liệu cảm biến từ luồng chính ---
    # Luồng chính có thể thực hiện các công việc khác hoặc chỉ đơn giản là duy trì
    # để các luồng daemon tiếp tục chạy.
    print("\n[MAIN] Các luồng gửi/nhận đã được khởi động.")
    print("[MAIN] Nhấn Ctrl+C để dừng chương trình.")

    try:
        while True:
            # Luồng chính có thể định kỳ đọc dữ liệu cảm biến mới nhất
            with data_lock:
                current_data = latest_sensor_data  # Lấy một bản sao an toàn

            if current_data.timestamp != 0:  # Chỉ in nếu đã có dữ liệu thực sự
                # print(f"[MAIN] Dữ liệu cảm biến mới nhất: {current_data}")
                pass  # Bỏ comment dòng trên để xem dữ liệu được in ra từ luồng chính

            time.sleep(0.5)  # Đọc dữ liệu mỗi 0.5 giây
    except KeyboardInterrupt:
        print("\n[MAIN] Ứng dụng đã dừng.")
