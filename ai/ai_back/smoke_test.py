import sys
import os

print("Testing imports for all modules...")
try:
    import main
    print("✅ main.py imported")
except Exception as e:
    print(f"❌ main.py failed import: {e}")

try:
    import audio_engine
    print("✅ audio_engine.py imported")
except Exception as e:
    print(f"❌ audio_engine.py failed import: {e}")

try:
    import obs_client
    print("✅ obs_client.py imported")
except Exception as e:
    print(f"❌ obs_client.py failed import: {e}")

try:
    import video_engine
    print("✅ video_engine.py imported")
except Exception as e:
    print(f"❌ video_engine.py failed import: {e}")

try:
    import verify_ws
    print("✅ verify_ws.py imported")
except Exception as e:
    print(f"❌ verify_ws.py failed import: {e}")

print("Import test complete.")
