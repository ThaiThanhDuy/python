import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("192.168.1.200", 1100))
s.send(b"TCP001")
resp = s.recv(1024)
print("📥", resp.decode())
s.close() 
