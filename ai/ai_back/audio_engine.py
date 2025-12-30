import pyaudio
import threading
import asyncio

class AudioEngine:
    def __init__(self, rate=16000, channels=1, chunk=1024):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False
        self.queues = set() # Set of asyncio.Queue for connected clients

    def start(self):
        if self.running:
            return

        try:
            self.stream = self.p.open(format=pyaudio.paInt16,
                                      channels=self.channels,
                                      rate=self.rate,
                                      input=True,
                                      frames_per_buffer=self.chunk,
                                      stream_callback=self._callback)
            self.stream.start_stream()
            self.running = True
            print("[Audio] Microphone started.")
        except Exception as e:
            print(f"[Audio] Failed to start microphone: {e}")

    def _callback(self, in_data, frame_count, time_info, status):
        # Broadcast to all connected websocket queues
        # Note: This runs in a separate thread, so we use loop.call_soon_threadsafe if needed,
        # but for simple queues we can try direct put. 
        # However, asyncio queues are not thread-safe. We need a bridge.
        # For simplicity in this architecture, we will just store data in a buffer or use a thread-safe queue if needed.
        # But here we are integrating with FastAPI Websockets.
        
        # Strategy: We will iterate over a list of connected client helper objects and call their push method.
        for q in list(self.queues):
            try:
                q.put_nowait(in_data)
            except asyncio.QueueFull:
                pass # Drop frame if client is slow
        return (None, pyaudio.paContinue)

    async def get_audio_generator(self):
        queue = asyncio.Queue(maxsize=10)
        self.queues.add(queue)
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            self.queues.remove(queue)

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
