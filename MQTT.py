import paho.mqtt.client as mqtt
import time

# Thông tin kết nối
broker_url = "c69aeca2d48441618b65f77f38e2d8dc.s1.eu.hivemq.cloud"
port = 8883
topic_subscribe = "#"  # Theo dõi tất cả các topic để xem phản hồi (tùy chọn)
topic_publish = "command/car"  # Topic để gửi lệnh điều khiển xe

# Thông tin đăng nhập
username = "hivemq.webclient.1746280264795"
password = "ay;Z9W0$L1k7fbS!xH?C"


# Các hàm callback
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối thành công đến MQTT broker!")
        client.subscribe(topic_subscribe)  # Theo dõi tất cả để xem phản hồi (tùy chọn)
    else:
        print(f"Kết nối thất bại với mã lỗi {rc}")


def on_message(client, userdata, msg):
    print(f"Nhận được tin nhắn từ topic '{msg.topic}': {msg.payload.decode()}")


def on_publish(client, userdata, mid):
    print(f"Đã gửi lệnh với message ID: {mid}")


# Tạo client MQTT
client = mqtt.Client()

# **Thêm username và password trước khi connect**
client.username_pw_set(username, password)

# Gán các hàm callback
client.on_connect = on_connect
client.on_message = on_message
client.on_publish = on_publish

# Thiết lập kết nối TLS
client.tls_set()

# Thực hiện kết nối
client.connect(broker_url, port, 60)

# Bắt đầu vòng lặp
client.loop_start()

try:
    while True:
        command = input(
            "Nhập lệnh điều khiển (forward, backward, left, right, quit): "
        ).lower()
        if command == "forward":
            client.publish(topic_publish, "FORWARD")
            print("Đã gửi lệnh: FORWARD")
        elif command == "backward":
            client.publish(topic_publish, "BACKWARD")
            print("Đã gửi lệnh: BACKWARD")
        elif command == "left":
            client.publish(topic_publish, "LEFT")
            print("Đã gửi lệnh: LEFT")
        elif command == "right":
            client.publish(topic_publish, "RIGHT")
            print("Đã gửi lệnh: RIGHT")
        elif command == "quit":
            break
        else:
            print(
                "Lệnh không hợp lệ. Vui lòng nhập forward, backward, left, right hoặc quit."
            )
        time.sleep(0.1)  # Tránh gửi lệnh quá nhanh
except KeyboardInterrupt:
    print("Ngắt kết nối...")
finally:
    client.loop_stop()
    client.disconnect()
    print("Đã ngắt kết nối khỏi MQTT broker.")
