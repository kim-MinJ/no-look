# ai/server.py
import asyncio
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from engine import NoLookEngine

app = FastAPI()

engine = NoLookEngine(webcam_id=0, transition_time=0.5, fps_limit=30.0)

clients: Set[WebSocket] = set()


class BoolPayload(BaseModel):
    value: bool


@app.on_event("startup")
async def startup():
    engine.start()
    asyncio.create_task(broadcast_state_loop())


@app.on_event("shutdown")
async def shutdown():
    engine.stop()


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


# ---------- HTTP Controls ----------
@app.post("/control/pause_fake")
def pause_fake(payload: BoolPayload):
    engine.set_pause_fake(payload.value)
    return {"ok": True, "pauseFake": payload.value}


@app.post("/control/force_real")
def force_real(payload: BoolPayload):
    engine.set_force_real(payload.value)
    return {"ok": True, "forceReal": payload.value}


@app.post("/control/reset_lock")
def reset_lock():
    engine.reset_lock()
    return {"ok": True, "lockedFake": False}


@app.get("/state")
def get_state():
    return engine.get_state()