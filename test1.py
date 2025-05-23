import cv2


# capture from camera at location 0
cap = cv2.VideoCapture(0)
# set the width and height, and UNSUCCESSFULLY set the exposure time
cap.set(cv2.CV_CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CV_CAP_PROP_FRAME_HEIGHT, 1024)
cap.set(cv2.CV_CAP_PROP_EXPOSURE, 0.1)

while True:
    ret, img = cap.read()
    cv2.imshow("input", img)
    # cv2.imshow("thresholded", imgray*thresh2)

    key = cv2.waitKey(10)
    if key == 27:
        break


cv2.destroyAllWindows()
cv2.VideoCapture(0).release()
