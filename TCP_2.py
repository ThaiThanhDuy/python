import socket
import threading
import time
import random  # Để tạo dữ liệu ngẫu nhiên

# --- Cấu hình kết nối TCP ---
STM32_IP = "192.168.77.200"  # <--- THAY ĐỔI ĐỊA CHỈ IP CỦA STM32 CỦA BẠN TẠI ĐÂY
PORT = 1100  # Cổng chung cho cả gửi và nhận

# Biến cờ để kiểm soát việc dừng các luồng
stop_threads = False

# --- CÁC THAM SỐ TỐI ƯU TỐC ĐỘ ---
# Giảm thời gian chờ nhận trên socket Python. Cần kshớp hoặc nhỏ hơn recvtimeout trên STM32.
PYTHON_SOCKET_TIMEOUT = 0.02  # 20ms

# Giảm thời gian delay trong luồng nhận. Task sẽ kiểm tra nhanh hơn.
RECEIVE_THREAD_SLEEP = 0.001  # 1ms

# Giảm tần suất gửi lệnh. STM32 càng nhanh thì có thể giảm càng nhiều.
SEND_COMMAND_INTERVAL = 0.05  # Gửi mỗi 50ms (20 lần/giây)


# --- Hàm xử lý việc nhận dữ liệu ---
def receive_data(sock):
    """
    Hàm này sẽ chạy trong một luồng riêng để liên tục nhận dữ liệu từ server.
    """
    print(f"Bắt đầu nhận dữ liệu từ {STM32_IP}:{PORT}...")
    while not stop_threads:
        try:
            data = sock.recv(1024)
            if data:
                print(f"[NHẬN]: {data.decode().strip()}")
            else:
                print("Server đã đóng kết nối.")
                break
        except socket.timeout:
            pass  # Timeout là bình thường khi không có dữ liệu đến, tiếp tục vòng lặp
        except ConnectionResetError:
            print("Kết nối đã bị đặt lại bởi server (mất kết nối).")
            break
        except Exception as e:
            print(f"Lỗi khi nhận dữ liệu: {e}")
            break
        # Giảm thời gian ngủ của luồng nhận
        time.sleep(RECEIVE_THREAD_SLEEP)


# --- Hàm xử lý việc gửi lệnh liên tục ---
def send_continuous_commands(sock):
    """
    Hàm này sẽ tự động gửi các lệnh VEL: giả lập sau mỗi khoảng thời gian.
    """
    print("Bắt đầu gửi lệnh liên tục...")
    while not stop_threads:
        try:
            # Tạo dữ liệu giả lập
            # linear_vel = round(random.uniform(-1.0, 1.0), 2)
            # angular_vel = round(random.uniform(-0.5, 0.5), 2)
            linear_vel = 1.0

            angular_vel = 0.0

            command = f"VEL:{linear_vel},{angular_vel}\r\n"

            sock.sendall(command.encode())
            print(f"[GỬI TỰ ĐỘNG]: {command.strip()}")

        except Exception as e:
            print(f"Lỗi khi gửi lệnh: {e}")
            break
        # Giảm thời gian chờ giữa các lần gửi
        time.sleep(SEND_COMMAND_INTERVAL)


# --- Hàm chính để thiết lập kết nối và khởi động các luồng ---
def main():
    global stop_threads
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Đặt timeout nhỏ cho socket
        sock.settimeout(PYTHON_SOCKET_TIMEOUT)

        print(f"Đang kết nối tới {STM32_IP}:{PORT}...")
        sock.connect((STM32_IP, PORT))
        print(f"Đã kết nối thành công tới {STM32_IP}:{PORT}")

        # Khởi tạo và bắt đầu luồng nhận dữ liệu
        receive_thread = threading.Thread(target=receive_data, args=(sock,))
        receive_thread.daemon = True
        receive_thread.start()

        # Khởi tạo và bắt đầu luồng gửi lệnh liên tục
        send_thread = threading.Thread(target=send_continuous_commands, args=(sock,))
        send_thread.daemon = True
        send_thread.start()

        print("\nChương trình đang chạy. Nhấn Ctrl+C để thoát.")
        while True:
            time.sleep(1)  # Giữ luồng chính hoạt động

    except ConnectionRefusedError:
        print(
            f"Lỗi: Kết nối bị từ chối. Đảm bảo STM32 đang chạy server TCP trên cổng {PORT} và có thể truy cập được."
        )
    except socket.timeout:
        print(f"Lỗi: Hết thời gian chờ kết nối tới {STM32_IP}:{PORT}.")
    except KeyboardInterrupt:
        print("\nĐã nhận lệnh Ctrl+C. Đang dừng chương trình...")
        stop_threads = True
        # Đợi các luồng con kết thúc trước khi đóng socket (tùy chọn)
        receive_thread.join(timeout=1.0)
        send_thread.join(timeout=1.0)
    except Exception as e:
        print(f"Một lỗi không mong muốn đã xảy ra: {e}")
    finally:
        if sock:
            print("Đóng socket.")
            sock.close()
        print("Chương trình kết thúc.")


if __name__ == "__main__":
    main()
