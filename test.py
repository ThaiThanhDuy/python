import socketio
from flask import Flask, request
from flask_cors import CORS
import eventlet
import eventlet.wsgi
import logging

 # Cấu hình logging để xem thêm thông tin
logging.basicConfig(level=logging.DEBUG)
sio_logger = logging.getLogger('socketio')
sio_logger.setLevel(logging.DEBUG)
wsgi_logger = logging.getLogger('wsgi')
wsgi_logger.setLevel(logging.DEBUG)

 # Tạo server Socket.IO
sio = socketio.Server(cors_allowed_origins='*', logger=sio_logger, engineio_logger=True)
app = Flask(__name__)
CORS(app)  # Cho phép mọi origin truy cập (dành cho Android)

 # Gắn Flask vào Socket.IO
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

@app.route('/')
def index():
  return 'Socket.IO server is running!'

@sio.event
def connect(sid, environ):
  print(f'Client connected: {sid}')
  logging.debug(f'Connect event - SID: {sid}, Environ: {environ}')

@sio.on('send_message')
def handle_message(sid, data):
  print(f'Received message from {sid}: {data}')
  logging.debug(f'send_message event - SID: {sid}, Data: {data}')
  # Gửi lại message cho client (nếu muốn)
  try:
   sio.emit('new_message', {'message': data['message']}, room=sid)
   logging.debug(f'Emitted new_message to SID: {sid}, Data: {{\'message\': {data["message"]}}}')
  except KeyError:
   logging.error(f'KeyError: "message" not found in data received from SID: {sid}, Data: {data}')
  except Exception as e:
   logging.error(f'Error emitting new_message: {e}')

@sio.event
def disconnect(sid):
  print(f'Client disconnected: {sid}')
  logging.debug(f'Disconnect event - SID: {sid}')

if __name__ == '__main__':
  host = '192.168.2.88'
  port = 8080
  print(f"🚀 Socket.IO server starting on http://{host}:{port}...")
  eventlet.wsgi.server(eventlet.listen((host, port)), app, log=wsgi_logger)