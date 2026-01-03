# ai/server.py
import asyncio
import os
import sys
from typing import Set, List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import NoLookEngine
from auto_macro_service import assistant_service


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ warmup 3분(180초) / rolling 3분(180초)
engine = NoLookEngine(
    webcam_id=0,
    transition_time=0.5,
    fps_limit=30.0,
    warmup_seconds=180,
    rolling_seconds=180,
    rolling_segment_seconds=2,
)

clients: Set[WebSocket] = set()


class BoolPayload(BaseModel):
    value: bool


class StringPayload(BaseModel):
    value: str


class KeywordsPayload(BaseModel):
    keywords: List[str]


@app.get("/health")
def health_check():
    return {"ok": True}


api_router = APIRouter(prefix="/api")


@api_router.post("/control/pause_fake")
def pause_fake(payload: BoolPayload):
    engine.set_pause_fake(payload.value)
    return {"ok": True, "pauseFake": payload.value}


@api_router.post("/control/force_real")
def force_real(payload: BoolPayload):
    engine.set_force_real(payload.value)
    return {"ok": True, "forceReal": payload.value}


@api_router.post("/control/transition")
def set_transition(payload: StringPayload):
    engine.set_transition_effect(payload.value)
    return {"ok": True, "transitionEffect": payload.value}


@api_router.post("/control/reset_lock")
def reset_lock():
    engine.reset_lock()
    return {"ok": True, "lockedFake": False}


@api_router.post("/control/assistant")
def control_assistant(payload: BoolPayload):
    if payload.value:
        assistant_service.start()
    else:
        assistant_service.stop()
    return {"ok": True, "assistantEnabled": payload.value}


@api_router.post("/control/stt/config")
def update_stt_config(payload: KeywordsPayload):
    """
    프론트엔드에서 받은 키워드 리스트로 STT 설정을 업데이트
    """
    success = engine.update_stt_config(payload.keywords)
    if success:
        print(f"✅ [Server] STT 키워드 업데이트됨: {payload.keywords}")
        return {"ok": True, "keywords": payload.keywords}
    else:
        print("❌ [Server] STT 설정 업데이트 실패 (엔진에 STT 없음)")
        return {"ok": False, "error": "STT not initialized"}


@api_router.get("/state")
def get_state():
    # ✅ "처음 접속" 트리거: 여기서 warmup 세션 시작
    engine.start_session_if_needed()
    return engine.get_state()


app.include_router(api_router)


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        engine.start_session_if_needed()
        init_state = engine.get_state()
        try:
            init_state["stt"] = assistant_service.get_transcript_state()
            init_state["assistantEnabled"] = assistant_service._running
        except Exception as e:
            print(f"⚠️ Init STT Error: {e}")
        await websocket.send_json(init_state)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


async def broadcast_state_loop():
    while True:
        if clients:
            engine.start_session_if_needed()
        state = engine.get_state()
        
        # ✅ STT 상태 병합
        try:
            state["stt"] = assistant_service.get_transcript_state()
            state["assistantEnabled"] = assistant_service._running
        except Exception as e:
            print(f"⚠️ STT State Error: {e}")

        dead = []
        for ws in list(clients):
            try:
                await ws.send_json(state)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)
        await asyncio.sleep(0.05)


@app.on_event("startup")
async def startup():
    engine.start()
    asyncio.create_task(broadcast_state_loop())


@app.on_event("shutdown")
async def shutdown():
    engine.stop()
    assistant_service.stop()


static_dir = resource_path("static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
