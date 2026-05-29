import socket

stm32_ip = "192.168.1.200"  # IP của STM32
stm32_port = 1100  # Port UDP STM32 đang bind
my_port = 5005  # Port máy tính sẽ nhận phản hồi (tùy chọn)

# Tạo UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Gán port cục bộ (nếu muốn rõ ràng)
sock.bind(("", my_port))

# Gửi gói UDP tới STM32
msg = "UDP01"  # Hoặc thử "UDP01" hoặc gì khác
sock.sendto(msg.encode(), (stm32_ip, stm32_port))
print(f"📤 Sent '{msg}' to STM32 at {stm32_ip}:{stm32_port}")

# Chờ phản hồi từ STM32
sock.settimeout(3.0)  # Timeout sau 3 giây
try:
    data, addr = sock.recvfrom(1024)  # Nhận dữ liệu từ STM32
    print(f"📥 Received from {addr}: {data.decode().strip()}")
except socket.timeout:
    print("⏱️ Timeout: Không nhận được phản hồi từ STM32.")

sock.close()
