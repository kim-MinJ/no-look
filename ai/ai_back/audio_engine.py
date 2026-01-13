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
        self.queues = set() # 연결된 클라이언트를 위한 asyncio.Queue 집합

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
        # 브로드캐스트: 연결된 모든 웹소켓 큐에 데이터 전송
        # 주의: 이 코드는 별도 스레드에서 실행되므로 thread-safe가 필요함.
        # 간단한 구조를 위해 여기서는 큐에 직접 넣거나 thread-safe 큐를 사용.
        # FastAPI 웹소켓과 통합되어 있음.
        
        # 전략: 연결된 클라이언트 큐 목록을 순회하며 데이터 푸시.
        for q in list(self.queues):
            try:
                q.put_nowait(in_data)
            except asyncio.QueueFull:
                pass # 클라이언트가 느리면 프레임 드롭
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
