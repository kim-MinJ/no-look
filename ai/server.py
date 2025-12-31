# ai/server.py
"""
Backend: AI Models Only
- MeetingBot (OpenAI)
- MacroBot (Gemini)
- MacroEngine (System Control)
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from bot import MeetingBot
from macro_bot import MacroBot
from macro_engine import MacroEngine

app = FastAPI()

# AI Services
meeting_bot = MeetingBot()
macro_bot = MacroBot()
macro_engine = MacroEngine()


class MacroPayload(BaseModel):
    text: str
    app: str = "zoom"


@app.on_event("startup")
async def startup():
    print("🤖 AI Backend Server Started")
    print("✅ OpenAI Bot Ready")
    print("✅ Gemini Macro Bot Ready")
    print("✅ Macro Engine Ready")


@app.websocket("/ws/ai")
async def ai_service(websocket: WebSocket):
    """
    AI Service WebSocket
    Handles:
    - Bot reactions (OpenAI)
    - AI suggestions (Gemini)
    """
    await websocket.accept()
    print("🔗 Frontend connected to AI service")
    
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            # OpenAI Bot Reaction
            if message_type == "reaction_request":
                print("🤖 Generating bot reaction...")
                reaction = meeting_bot.get_reaction()
                await websocket.send_json({
                    "type": "reaction",
                    "text": reaction
                })
                print(f"✅ Sent reaction: {reaction}")
            
            # Gemini AI Suggestion
            elif message_type == "suggestion_request":
                transcript = data.get("transcript", "")
                print(f"🤖 Generating AI suggestion for: {transcript[:50]}...")
                suggestion = macro_bot.get_suggestion(transcript)
                await websocket.send_json({
                    "type": "suggestion",
                    "text": suggestion
                })
                print(f"✅ Sent suggestion: {suggestion}")
            
            else:
                print(f"⚠️ Unknown message type: {message_type}")
                
    except WebSocketDisconnect:
        print("❌ Frontend disconnected from AI service")


@app.websocket("/ws/state")
async def state_websocket(websocket: WebSocket):
    """
    Legacy state WebSocket endpoint
    Kept for frontend compatibility (Dashboard.jsx)
    """
    await websocket.accept()
    print("🔗 Frontend connected to /ws/state")
    
    try:
        while True:
            # Just keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("❌ Frontend disconnected from /ws/state")


@app.get("/state")
def get_state():
    """
    Legacy state HTTP endpoint
    Returns minimal state for frontend compatibility
    """
    return {
        "mode": "AI_READY",
        "services": {
            "openai": meeting_bot.client is not None,
            "gemini": macro_bot.model is not None
        }
    }


@app.post("/control/macro")
def trigger_macro(payload: MacroPayload):
    """
    Execute macro (keyboard automation)
    """
    print(f"⌨️ Macro request: {payload.text} → {payload.app}")
    success = macro_engine.type_text(payload.text, payload.app)
    return {
        "ok": success,
        "message": f"Typed to {payload.app}" if success else "Failed"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "openai_bot": meeting_bot.client is not None,
            "gemini_bot": macro_bot.model is not None,
            "macro_engine": True
        }
    }


@app.get("/")
def root():
    return {
        "message": "No-Look AI Backend",
        "endpoints": {
            "websocket": "/ws/ai",
            "macro": "POST /control/macro",
            "health": "GET /health"
        }
    }