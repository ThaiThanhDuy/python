import socket
import threading
import time

# --- Cấu hình kết nối TCP ---
STM32_IP = "192.168.77.200"  # Địa chỉ IP STM32
PORT = 1100  # Cổng TCP của STM32

stop_threads = False

# Thời gian chờ tối đa khi đọc socket (giảm lag)
PYTHON_SOCKET_TIMEOUT = 0.02  # 20 ms
RECEIVE_THREAD_SLEEP = 0.001  # 1 ms


# --- Hàm nhận dữ liệu ---
def receive_data(sock):
    print(f"Bắt đầu nhận dữ liệu từ {STM32_IP}:{PORT}...")
    while not stop_threads:
        try:
            data = sock.recv(1024)
            if data:
                print(f"[NHẬN]: {data.decode(errors='ignore').strip()}")
            else:
                print("Server đã đóng kết nối.")
                break
        except socket.timeout:
            pass  # Không có dữ liệu thì bỏ qua
        except ConnectionResetError:
            print("Kết nối bị reset bởi server.")
            break
        except Exception as e:
            print(f"Lỗi khi nhận dữ liệu: {e}")
            break
        time.sleep(RECEIVE_THREAD_SLEEP)


# --- Hàm chính ---
def main():
    global stop_threads
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(PYTHON_SOCKET_TIMEOUT)

        print(f"Đang kết nối tới {STM32_IP}:{PORT}...")
        sock.connect((STM32_IP, PORT))
        print("Kết nối thành công.")

        # Chạy luồng nhận
        receive_thread = threading.Thread(target=receive_data, args=(sock,))
        receive_thread.daemon = True
        receive_thread.start()

        print("\nĐang nhận dữ liệu... Nhấn Ctrl+C để thoát.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nDừng chương trình...")
        stop_threads = True
        receive_thread.join(timeout=1.0)
    except Exception as e:
        print(f"Lỗi: {e}")
    finally:
        if sock:
            sock.close()
        print("Chương trình kết thúc.")


if __name__ == "__main__":
    main()
