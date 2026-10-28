import cv2
import base64

class VisionSource:
    def __init__(self, source=0):
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            print("Error: Could not open video source.")

    def capture_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            print("Error: Failed to capture frame.")
            return None

        frame_resized = cv2.resize(frame, (640, 480))

        success, buffer = cv2.imencode('.jpg', frame_resized)
        if not success:
            return None

        base64_string = base64.b64encode(buffer).decode('utf-8')
        
        return base64_string

    def close(self):
        self.cap.release()

if __name__ == "__main__":
    eye = VisionSource(0) 
    frame_b64 = eye.capture_frame()
    
    if frame_b64:
        print(f"Success! Captured frame encoded to Base64 (Length: {len(frame_b64)})")
    
    eye.close()
