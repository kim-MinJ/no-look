# ai/server.py
import asyncio
import os
import sys
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json

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

# ✅ warmup 1분(60초) / rolling 1분(60초)
engine = NoLookEngine(
    webcam_id=0,
    transition_time=0.5,
    fps_limit=30.0,
    warmup_seconds=60,
    rolling_seconds=60,

    rolling_segment_seconds=2,
)

clients: Set[WebSocket] = set()


class BoolPayload(BaseModel):
    value: bool


class StringPayload(BaseModel):
    value: str

class ConfigPayload(BaseModel):
    """config.json 전체 구조"""
    triggers: dict
    personalization: dict
    settings: dict
    actions: dict


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


@api_router.post("/macro/type")
def macro_type(payload: StringPayload):
    """지정된 텍스트를 줌 채팅창(활성화된 창)에 타이핑 및 전송"""
    try:
        if assistant_service.automator:
            import threading
            threading.Thread(
                target=assistant_service.automator.send_to_zoom,
                args=(payload.value,),
                daemon=True
            ).start()
            return {"ok": True, "message": "전송 요청 완료"}
        else:
            return {"ok": False, "message": "Automator가 초기화되지 않았습니다."}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@api_router.get("/config")
def get_config():
    """현재 config.json 내용을 읽어서 반환"""
    try:
        # 현재 파일(server.py) 기준으로 상대 경로 사용
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "sound", "config.json")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        return config_data
    except Exception as e:
        print(f"❌ [Config API] 설정 읽기 실패: {e}")
        return {"ok": False, "detail": str(e)}


@api_router.post("/config")
def save_config(payload: ConfigPayload):
    """설정을 config.json에 저장하고 실시간 반영"""
    try:
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "sound", "config.json")
        config_dict = payload.dict()
        
        # config.json 저장
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=4)
        
        # STT 엔진에 실시간 반영
        if assistant_service._initialized and assistant_service.ears:
            assistant_service.ears.reload_config()
        
        return {"ok": True, "message": "설정이 저장되고 반영되었습니다."}
    except Exception as e:
        print(f"❌ [Config API] 설정 저장 실패: {e}")
        return {"ok": False, "detail": str(e)}


def get_full_engine_state():
    """엔진 상태와 STT 비서 상태를 모두 병합하여 반환"""
    state = engine.get_state()
    try:
        state["stt"] = assistant_service.get_transcript_state()
        state["assistantEnabled"] = assistant_service._running
    except Exception as e:
        print(f"⚠️ State Merge Error: {e}")
    return state


@api_router.get("/state")
def get_state():
    engine.start_session_if_needed()
    return get_full_engine_state()


app.include_router(api_router)


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        engine.start_session_if_needed()
        init_state = get_full_engine_state()
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
        
        state = get_full_engine_state()

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
