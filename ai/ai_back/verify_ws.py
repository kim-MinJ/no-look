import asyncio
import websockets
import json
import sys

AUDIO_WS_URL = "ws://localhost:8000/stream/audio"
CONTROL_WS_URL = "ws://localhost:8000/ws/control"

async def test_audio():
    print(f"[Audio] Connecting to {AUDIO_WS_URL}...")
    try:
        async with websockets.connect(AUDIO_WS_URL) as websocket:
            print("[Audio] Connected! Waiting for data...")
            count = 0
            async for message in websocket:
                count += 1
                if count % 10 == 0:
                    print(f"[Audio] Received {len(message)} bytes (Packet #{count})")
                
                # Test for 50 packets then stop
                if count >= 50:
                    print("[Audio] Verified successfully!")
                    break
    except Exception as e:
        print(f"[Audio] Error: {e}")

async def test_control():
    print(f"[Control] Connecting to {CONTROL_WS_URL}...")
    try:
        async with websockets.connect(CONTROL_WS_URL) as websocket:
            print("[Control] Connected! Sending 'gaze_off' trigger...")
            
            # Send Test Trigger
            msg = {"type": "trigger", "event": "gaze_off"}
            await websocket.send(json.dumps(msg))
            print(f"[Control] Sent: {msg}")
            
            # Wait for response
            response = await websocket.recv()
            print(f"[Control] Received: {response}")
            
            print("[Control] Verified successfully!")
            
    except Exception as e:
        print(f"[Control] Error: {e}")

async def main():
    print("=== Testing Python Backend WebSockets ===")
    
    task1 = asyncio.create_task(test_audio())
    task2 = asyncio.create_task(test_control())
    
    await asyncio.gather(task1, task2)
    print("=== Test Complete ===")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
