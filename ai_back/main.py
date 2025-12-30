import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from audio_engine import AudioEngine
from obs_client import OBSClient
import asyncio
import os
from dotenv import load_dotenv

# Load Env
load_dotenv()
OBS_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")

app = FastAPI()

# Components
audio_engine = AudioEngine()
obs_client = OBSClient(password=OBS_PASSWORD)

# Start Audio on startup
@app.on_event("startup")
async def startup_event():
    audio_engine.start()

@app.on_event("shutdown")
async def shutdown_event():
    audio_engine.stop()
    obs_client.disconnect()



# --- Audio Stream (WebSocket) ---
@app.websocket("/stream/audio")
async def audio_feed(websocket: WebSocket):
    await websocket.accept()
    generator = audio_engine.get_audio_generator()
    try:
        async for chunk in generator:
            await websocket.send_bytes(chunk)
    except WebSocketDisconnect:
        print("Audio Client disconnected")

# --- Control Socket ---
@app.websocket("/ws/control")
async def control_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # Expected format: {"type": "trigger", "event": "gaze_off"}
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
            
            # Echo back status or confirmation
            await websocket.send_json({"status": "ok", "echo": data})
            
    except WebSocketDisconnect:
        print("Control Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
