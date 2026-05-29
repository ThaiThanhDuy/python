import paho.mqtt.client as mqtt
import time

# Cấu hình MQTT Broker
MQTT_BROKER = "c69aeca2d48441618b65f77f38e2d8dc.s1.eu.hivemq.cloud"  # Thay thế bằng địa chỉ MQTT broker của bạn
MQTT_PORT = 8883
MQTT_TOPIC = "car/control"  # Topic MQTT để nhận lệnh điều khiển
MQTT_USERNAME = "hivemq.webclient.1745246142729"  # Thay thế bằng username của bạn nếu có
MQTT_PASSWORD = "#S9*y61bY;iG0&uUJfhR"  # Thay thế bằng password của bạn nếu có

# --- CÁC HÀM ĐIỀU KHIỂN ĐỘNG CƠ (CẦN ĐIỀU CHỈNH CHO PHÙ HỢP VỚI PHẦN CỨNG CỦA BẠN) ---
def move_forward():
    print("Di chuyển về phía trước")
    # Thêm code điều khiển động cơ để đi tới

def move_back():
    print("Di chuyển về phía sau")
    # Thêm code điều khiển động cơ để đi lùi

def turn_left():
    print("Rẽ trái")
    # Thêm code điều khiển động cơ để rẽ trái

def turn_right():
    print("Rẽ phải")
    # Thêm code điều khiển động cơ để rẽ phải
# -----------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Đã kết nối thành công đến MQTT Broker!")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Kết nối thất bại, mã lỗi {rc}")

def on_message(client, userdata, msg):
    command = msg.payload.decode('utf-8')
    print(f"Nhận được lệnh: {command}")
    if command == "forward":
        move_forward()
    elif command == "back":
        move_back()
    elif command == "left":
        turn_left()
    elif command == "right":
        turn_right()

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    #client = mqtt.Client(client_id="python_car_controller", callback_api_version=mqtt.CallbackAPIVersion.VERSION1) # Thêm client_id

    # Thiết lập thông tin đăng nhập nếu cần
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()  # Duy trì kết nối và lắng nghe tin nhắn

    except Exception as e:
        print(f"Đã xảy ra lỗi: {e}")