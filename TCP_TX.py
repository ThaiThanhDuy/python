import socket
import time

STM32_IP = "192.168.1.200"  # Cập nhật đúng IP STM32
STM32_PORT = 1100  # Phải khớp cổng với `netconn_bind`


def send_cmd_vel(linear, angular):
    try:
        # Tạo socket TCP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect((STM32_IP, STM32_PORT))

            # Format chuỗi VEL:<linear>,<angular>
            message = f"VEL:{linear:.2f},{angular:.2f}"
            print(f"➡️  Gửi: {message}")
            sock.sendall(message.encode())

            # Nếu STM32 có gửi phản hồi thì nhận
            try:
                response = sock.recv(128).decode().strip()
                print(f"⬅️  Phản hồi: {response}")
            except socket.timeout:
                print("⏱️  Không có phản hồi")

    except (ConnectionRefusedError, TimeoutError) as e:
        print(f"❌ Kết nối lỗi: {e}")
    except Exception as e:
        print(f"⚠️  Lỗi khác: {e}")


if __name__ == "__main__":
    # Test gửi lệnh nhiều lần
    for i in range(5):
        send_cmd_vel(0.2 * i, -0.1 * i)
        time.sleep(1)  # Giãn cách giữa các lần gửi
