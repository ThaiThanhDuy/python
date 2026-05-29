import socket

STM32_IP = "192.168.1.200"  # IP của STM32
STM32_PORT = 1200  # Cổng mà STM32 đang lắng nghe

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((STM32_IP, STM32_PORT))
    print(f"[Client] ✅ Connected to STM32:{STM32_PORT}")

    try:
        while True:
            data = s.recv(128)
            if not data:
                print("[Client] ❌ Connection closed by STM32")
                break
            print("[Client] 📥 Data received:", data.decode().strip())
    except KeyboardInterrupt:
        print("Stopped by user")
