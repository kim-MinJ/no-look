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
            with open("verify_log.txt", "w") as f:
                f.write("[Audio] Connected! Waiting for data...\n")
            count = 0
            async for message in websocket:
                count += 1
                if count % 10 == 0:
                    msg = f"[Audio] Received {len(message)} bytes (Packet #{count})"
                    print(msg)
                    with open("verify_log.txt", "a") as f:
                        f.write(msg + "\n")
                
                # 50개 패킷 테스트 후 중지
                if count >= 50:
                    print("[Audio] Verified successfully!")
                    with open("verify_log.txt", "a") as f:
                        f.write("[Audio] Verified successfully!\n")
                    break
    except Exception as e:
        print(f"[Audio] Error: {e}")
        with open("verify_log.txt", "a") as f:
            f.write(f"[Audio] Error: {e}\n")

async def test_control():
    print(f"[Control] Connecting to {CONTROL_WS_URL}...")
    try:
        async with websockets.connect(CONTROL_WS_URL) as websocket:
            print("[Control] Connected! Sending 'gaze_off' trigger...")
            with open("verify_log.txt", "a") as f:
                f.write("[Control] Connected! Sending 'gaze_off' trigger...\n")
            
            # 테스트 트리거 전송
            msg = {"type": "trigger", "event": "gaze_off"}
            await websocket.send(json.dumps(msg))
            print(f"[Control] Sent: {msg}")
            
            # 응답 대기
            response = await websocket.recv()
            print(f"[Control] Received: {response}")
            with open("verify_log.txt", "a") as f:
                f.write(f"[Control] Received: {response}\n")
            
            print("[Control] Verified successfully!")
            with open("verify_log.txt", "a") as f:
                f.write("[Control] Verified successfully!\n")
            
    except Exception as e:
        print(f"[Control] Error: {e}")
        with open("verify_log.txt", "a") as f:
            f.write(f"[Control] Error: {e}\n")

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
