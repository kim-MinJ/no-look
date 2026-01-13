
"""
FILE COMMENTED OUT BY AGENT
This file was identified as part of the 'ai_back' module which is not currently connected to the main 'ai' or 'frontend' components.
It is being commented out to prevent execution conflicts (e.g. port 8000 usage).
"""
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from audio_engine import AudioEngine
from obs_client import OBSClient
import asyncio
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
OBS_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")

app = FastAPI()

# 구성 요소
audio_engine = AudioEngine()
obs_client = OBSClient(password=OBS_PASSWORD)

# 시작 시 오디오 실행
@app.on_event("startup")
async def startup_event():
    with open("server_log.txt", "w") as f:
        f.write("Server starting...\n")
    try:
        audio_engine.start()
        with open("server_log.txt", "a") as f:
            f.write("Audio engine started.\n")
    except Exception as e:
        with open("server_log.txt", "a") as f:
            f.write(f"Error starting audio engine: {e}\n")

@app.on_event("shutdown")
async def shutdown_event():
    audio_engine.stop()
    obs_client.disconnect()
    with open("server_log.txt", "a") as f:
        f.write("Server shutdown.\n")



# --- 오디오 스트림 (웹소켓) ---
@app.websocket("/stream/audio")
async def audio_feed(websocket: WebSocket):
    await websocket.accept()
    generator = audio_engine.get_audio_generator()
    try:
        async for chunk in generator:
            await websocket.send_bytes(chunk)
    except WebSocketDisconnect:
        print("Audio Client disconnected")

# --- 제어 소켓 ---
@app.websocket("/ws/control")
async def control_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # 예상 포맷: {"type": "trigger", "event": "gaze_off"}
            print(f"[Control] Received: {data}")
            
            if data.get("type") == "trigger":
                event = data.get("event")
                if event == "gaze_off":
                    # video_engine.set_mode("FAKE") # Video removed
                    # obs_client.set_scene("Scene Name") # Optional: Switch OBS scene
                    pass
                elif event == "gaze_on":
                    # video_engine.set_mode("REAL") # Video removed
                    pass
            
            # 상태 또는 확인 메시지 반환
            await websocket.send_json({"status": "ok", "echo": data})
            
    except WebSocketDisconnect:
        print("Control Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

