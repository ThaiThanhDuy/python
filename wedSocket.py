import socketio
import eventlet

sio = socketio.Server(async_mode='eventlet')
app = socketio.WSGIApp(sio)

@sio.event
def connect(sid, environ):
    print(f'Client connected: {sid}')

@sio.event
def disconnect(sid):
    print(f'Client disconnected: {sid}')

@sio.on('send_message')
def handle_message(sid, data):
    print(f'Received message from {sid}: {data}')
    # Gửi lại tin nhắn cho tất cả các client khác (tùy chọn)
    sio.emit('new_message', data, room=sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)
    print("Socket.IO server listening on port 5000")