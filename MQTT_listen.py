import cv2
import paho.mqtt.client as mqtt
import time

# Thông tin kết nối MQTT
broker_url = "c69aeca2d48441618b65f77f38e2d8dc.s1.eu.hivemq.cloud"
port = 8883
topic_subscribe_command = "command/car"  # Topic nhận lệnh
topic_publish_camera = "camera/stream"  # Topic gửi hình ảnh

# Thông tin đăng nhập
username = "hivemq.webclient.1746280264795"
password = "ay;Z9W0$L1k7fbS!xH?C"

# Tạo client MQTT
client = mqtt.Client()
client.username_pw_set(username, password)


# Hàm callback khi kết nối
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối thành công đến MQTT broker!")
        client.subscribe(topic_subscribe_command)  # Subscribe topic điều khiển
    else:
        print(f"Kết nối thất bại với mã lỗi {rc}")


# Hàm callback khi nhận được tin nhắn
def on_message(client, userdata, msg):
    if msg.topic == topic_subscribe_command:
        command = msg.payload.decode().upper()
        print(f"Nhận được lệnh: {command}")
        # Thêm logic điều khiển xe ở đây dựa trên 'command'


# Hàm callback khi đăng ký topic thành công
def on_subscribe(client, userdata, mid, granted_qos):
    print(f"Đã đăng ký topic: {topic_subscribe_command} với QoS: {granted_qos}")


# Gán các hàm callback
client.on_connect = on_connect
client.on_message = on_message
client.on_subscribe = on_subscribe

# Thiết lập kết nối TLS
client.tls_set()

# Thực hiện kết nối
client.connect(broker_url, port, 60)

# Mở camera
cap = cv2.VideoCapture(0)  # Thay đổi index nếu cần

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Không thể đọc frame từ camera.")
            break

        # Mã hóa frame thành JPEG
        _, img_encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        data_to_send = img_encoded.tobytes()

        # Publish frame lên topic camera
        client.publish(topic_publish_camera, payload=data_to_send, qos=0)
        print(
            f"Đã gửi frame ảnh ({len(data_to_send)} bytes) lên topic: {topic_publish_camera}"
        )

        time.sleep(0.1)  # Gửi mỗi 100ms (điều chỉnh tùy ý)

        # Duy trì vòng lặp MQTT để xử lý tin nhắn đến
        client.loop(timeout=0.01)  # Kiểm tra tin nhắn đến mỗi 10ms

except KeyboardInterrupt:
    print("Dừng script.")
finally:
    cap.release()
    client.disconnect()
