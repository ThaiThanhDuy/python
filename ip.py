import socket

# Lấy địa chỉ IP cục bộ của laptop (có thể có nhiều interface)
hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)
print(f"Địa chỉ IP cục bộ của laptop: {local_ip}")

# Định nghĩa địa chỉ IP và cổng muốn kết nối đến
#target_ip = local_ip
target_ip = "0.0.0.0"
target_port = 5000  # Ví dụ một cổng nào đó đang được lắng nghe

try:
    # Tạo một socket TCP
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Thiết lập thời gian chờ kết nối (tùy chọn)
    client_socket.settimeout(5)

    # Kết nối đến địa chỉ IP và cổng
    client_socket.connect((target_ip, target_port))
    print(f"Đã kết nối thành công đến {target_ip}:{target_port}")

    # Gửi và nhận dữ liệu (ví dụ đơn giản)
    message = "Xin chào từ Python!"
    client_socket.sendall(message.encode('utf-8'))
    print(f"Đã gửi: {message}")

    data = client_socket.recv(1024)
    print(f"Đã nhận: {data.decode('utf-8')}")

except socket.timeout:
    print(f"Kết nối đến {target_ip}:{target_port} bị hết thời gian chờ.")
except ConnectionRefusedError:
    print(f"Không thể kết nối đến {target_ip}:{target_port}. Kết nối bị từ chối.")
except Exception as e:
    print(f"Đã xảy ra lỗi: {e}")
finally:
    # Đóng kết nối
    if 'client_socket' in locals():
        client_socket.close()