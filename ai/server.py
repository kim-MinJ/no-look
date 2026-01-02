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

from engine import NoLookEngine

# =============================================================================
# PyInstaller resource path helper
# =============================================================================
def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    In PyInstaller onedir/onefile mode, files are extracted to sys._MEIPASS.
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# =============================================================================
# FastAPI App Setup
# =============================================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처 허용 (개발용)
    allow_credentials=True,
    allow_methods=["*"],  # 모든 메소드 허용 (GET, POST, OPTIONS 등)
    allow_headers=["*"],
)

engine = NoLookEngine(webcam_id=0, transition_time=0.5, fps_limit=30.0)

clients: Set[WebSocket] = set()


class BoolPayload(BaseModel):
    value: bool


class StringPayload(BaseModel):
    value: str


# =============================================================================
# Health Check (root level - for Electron to poll)
# =============================================================================
@app.get("/health")
def health_check():
    return {"ok": True}


# =============================================================================
# API Router (all endpoints under /api prefix)
# =============================================================================
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


@api_router.get("/state")
def get_state():
    return engine.get_state()


# Include the API router
app.include_router(api_router)


# =============================================================================
# WebSocket (keep at root /ws/state for compatibility)
# =============================================================================
@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        # 연결 직후 현재 상태 1회 푸시
        await websocket.send_json(engine.get_state())
        while True:
            # 프론트가 ping 보내도 되고 안 보내도 됨
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


async def broadcast_state_loop():
    """
    상태를 주기적으로 모든 클라이언트에 push.
    프론트는 mode/ratio/lockedFake/reasons만 써도 OK.
    """
    while True:
        state = engine.get_state()
        dead = []
        for ws in list(clients):
            try:
                await ws.send_json(state)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)
        await asyncio.sleep(0.05)  # 20fps


# =============================================================================
# Lifecycle Events
# =============================================================================
@app.on_event("startup")
async def startup():
    engine.start()
    asyncio.create_task(broadcast_state_loop())


@app.on_event("shutdown")
async def shutdown():
    engine.stop()


# =============================================================================
# Static Files (React build) - mounted last to catch-all
# =============================================================================
# Mount static files AFTER all API routes are registered
# This serves the React build from /static directory
static_dir = resource_path("static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# =============================================================================
# Entry point for development
# =============================================================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)