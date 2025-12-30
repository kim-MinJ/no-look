import pyvirtualcam
import numpy as np
import cv2
import base64
import threading
import time
import queue
from flask import Flask
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 큐를 사용하여 가장 최신 프레임 데이터만 보관 (지연 방지)
frame_queue = queue.Queue(maxsize=1)

# 가상 카메라 설정
WIDTH, HEIGHT = 1280, 720
FPS = 30

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('video_frame')
def handle_frame(data):
    try:
        # 데이터 수신 즉시 큐에 넣음 (이전 데이터는 버림 - maxsize=1)
        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass
        frame_queue.put_nowait(data)
    except Exception as e:
        print(f"Error receiving frame: {e}")

def camera_thread():
    print("Camera output thread started.")
    last_processed_frame = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    
    try:
        with pyvirtualcam.Camera(width=WIDTH, height=HEIGHT, fps=FPS) as cam:
            print(f'Virtual Camera device: {cam.device}')
            while True:
                # 1. 큐에서 새로운 데이터 확인
                try:
                    data = frame_queue.get_nowait()
                    
                    # 2. 데이터 디코딩 및 처리 (무거운 작업을 여기서 수행)
                    if isinstance(data, str) and data.startswith('data:image'):
                        header, encoded = data.split(",", 1)
                        data = base64.b64decode(encoded)
                    
                    nparr = np.frombuffer(data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        frame = cv2.resize(frame, (WIDTH, HEIGHT))
                        last_processed_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                except queue.Empty:
                    # 새로운 프레임이 없으면 이전 프레임 유지
                    pass
                except Exception as e:
                    print(f"Frame processing error: {e}")

                # 3. 항상 일정한 간격으로 송출
                cam.send(last_processed_frame)
                cam.sleep_until_next_frame()
                
    except Exception as e:
        print(f"CRITICAL ERROR in camera thread: {e}")

if __name__ == '__main__':
    # 카메라 송출을 별도 스레드에서 무한 루프로 실행
    threading.Thread(target=camera_thread, daemon=True).start()
    
    # SocketIO 서버 실행
    socketio.run(app, host='127.0.0.1', port=5000)
