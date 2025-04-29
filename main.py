# Thu vien
import cv2
import re
import numpy as np

# Khoi tao đoi tuong đe truy cap vao camera mac đinh (camera 0)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Set frame width to 640
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # Set frame height to 480
# Khoi tao đoi tuong phat hien ma QR
detector = cv2.QRCodeDetector()

print("Reading QR code using Raspberry Pi camera")

while True:
    # Lay mot khung hinh (frame) tu camera
    _, img = cap.read()

    # Phat hien, luu noi dung, vi tri cac ma QR
    retval, data, decoded_points, _ = detector.detectAndDecodeMulti(img)

    # Neu co ma QR se tien hanh xu ly
    if retval:
        # Lap qua tung i QR phat hien va cac toa do cua ma QR 
        for i, points in enumerate(decoded_points):
            # Chuyen đoi toa do cac điem goc tu kieu float sang int
            points = points.astype(int)
            # Ve khung vien xung quanh ma QR
            for j in range(len(points)):
                cv2.line(img, tuple(points[j]), tuple(points[(j+1) % len(points)]), color=(255,0, 0), thickness=2)
            # Hien thi du lieu ma QR tren hinh anh
            cv2.putText(img, data[i], (int(points[0][0]), int(points[0][1]) - 10), cv2.FONT_HERSHEY_SIMPLEX,0.5, (0, 255, 0), 2)
            # In du lieu ma QR
            print("Data found: " + data[i])
    
    # Hien thi hinh anh kem voi cac ma QR đuoc phat hien
    cv2.imshow("code detector", img)
    
    # Nhan phim 'q' đe thoat
    if cv2.waitKey(1) == ord("q"):
        break
    
# Giai phong camera sau khi ket thuc su dung
cap.release()
# Dong tat ca cac cua so hien thi hinh anh
cv2.destroyAllWindows()