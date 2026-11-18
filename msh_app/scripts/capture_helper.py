import cv2
import os
from datetime import datetime


def capture_stream(out_dir: str = "captured", camera_index: int = 0):
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("無法開啟攝影機")
        return
    print("按 s 儲存當前畫面，按 q 離開")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("讀取影像失敗")
            break
        cv2.imshow("capture", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('s'):
            fname = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
            path = os.path.join(out_dir, fname)
            cv2.imwrite(path, frame)
            print("已儲存", path)
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    capture_stream()
