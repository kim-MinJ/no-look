# ai/server_main.py
"""
PyInstaller entry point for the No-Look FastAPI server.
Localhost only: 127.0.0.1
"""
import argparse
import uvicorn

from server import app

SERVER_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    port = args.port
    print(f"Starting No-Look Server at http://{SERVER_HOST}:{port}")
    print("Press Ctrl+C to stop...")

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=port,
        log_level="info",
        loop="asyncio",
        http="h11",
        ws="websockets",
        lifespan="on",
    )


if __name__ == "__main__":
    main()
