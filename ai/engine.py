import os
import time
import threading
from typing import Any, Dict, List, Optional

import cv2

from detector import DistractionDetector
from generator import StreamGenerator
from bridge import VirtualCam
from bot import MeetingBot


class NoLookEngine:
    """
    - 웹캠을 단독 점유 (OpenCV)
    - detector로 상태 판단
    - generator로 fake 프레임/블렌딩
    - VirtualCam으로 출력
    - 최신 상태(state)를 서버가 가져갈 수 있게 제공
    """

    def __init__(
        self,
        webcam_id: int = 0,
        fake_video_path: Optional[str] = None,
        transition_time: float = 0.5,
        fps_limit: Optional[float] = None,  # None이면 제한 없음
    ):
        self.webcam_id = webcam_id
        self.transition_time = float(transition_time)
        self.fps_limit = fps_limit

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.fake_video_path = fake_video_path or os.path.join(base_dir, "assets", "fake_sample.mp4")

        # modules
        self.detector = DistractionDetector()
        self.generator = StreamGenerator(self.fake_video_path)
        self.bot = MeetingBot()

        # runtime
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.cap: Optional[cv2.VideoCapture] = None
        self.bridge: Optional[VirtualCam] = None

        # state machine
        self.mode = "REAL"  # "REAL" or "FAKE"
        self.trans_start = time.time()

        # latches / controls
        self.locked_fake = False
        self.pause_fake_playback = False
        self.force_real = False

        self.last_fake_frame = None  # pause용

        # latest exported state (server will read this)
        self._state: Dict[str, Any] = {
            "mode": "REAL",
            "ratio": 0.0,
            "lockedFake": False,
            "pauseFake": False,
            "forceReal": False,
            "reasons": [],
            "pitch": None,
            "timestamp": time.time(),
            "reaction": None,
        }

    # ---------- public control API (HTTP가 호출) ----------
    def set_pause_fake(self, value: bool) -> None:
        with self._lock:
            self.pause_fake_playback = bool(value)

    def set_force_real(self, value: bool) -> None:
        with self._lock:
            self.force_real = bool(value)
            if self.force_real:
                # 강제로 REAL로 갈 때는 전환 애니메이션 새로 시작
                if self.mode != "REAL":
                    self.mode = "REAL"
                    self.trans_start = time.time()

    def reset_lock(self) -> None:
        with self._lock:
            self.locked_fake = False
            # 락 풀면 현재 모드도 REAL로 전환 시작(원하면 여기 정책 바꿔도 됨)
            if self.mode != "REAL":
                self.mode = "REAL"
                self.trans_start = time.time()

    def get_state(self) -> Dict[str, Any]:
        # 서버가 상태 읽을 때 사용
        with self._lock:
            return dict(self._state)

    # ---------- lifecycle ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        # VirtualCam은 네 구현에 따라 close가 있을 수도/없을 수도
        self.bridge = None

    # ---------- internal loop ----------
    def _run(self) -> None:
        self.cap = cv2.VideoCapture(self.webcam_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Webcam open failed: {self.webcam_id}")

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.bridge = VirtualCam(width, height)

        last_frame_time = time.time()

        while not self._stop_event.is_set():
            ret, real_frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # (1) detect
            is_distracted, reasons = self.detector.is_distracted(real_frame)

            with self._lock:
                force_real = self.force_real
                pause_fake = self.pause_fake_playback

                # (2) latch(한번 딴짓이면 FAKE 고정) - force_real이면 latch 무시
                reaction = None
                if (not force_real) and is_distracted and (not self.locked_fake):
                    self.locked_fake = True
                    # 필요하면 여기서 한번만 봇 반응 생성
                    reaction = self.bot.get_reaction()

                # (3) target mode
                target_mode = "REAL" if force_real else ("FAKE" if self.locked_fake else "REAL")

                # (4) transition start
                if target_mode != self.mode:
                    self.mode = target_mode
                    self.trans_start = time.time()

                # (5) ratio
                elapsed = time.time() - self.trans_start
                progress = min(elapsed / self.transition_time, 1.0)
                ratio = progress if self.mode == "FAKE" else (1.0 - progress)

            # (6) generate fake frame (pause면 마지막 프레임 고정)
            if self.mode == "FAKE":
                if pause_fake and (self.last_fake_frame is not None):
                    fake_frame = self.last_fake_frame
                else:
                    fake_frame = self.generator.get_fake_frame()
                    if fake_frame is None:
                        fake_frame = real_frame.copy()
                    else:
                        self.last_fake_frame = fake_frame

                # resize to match
                if fake_frame.shape[:2] != real_frame.shape[:2]:
                    fake_frame = cv2.resize(fake_frame, (real_frame.shape[1], real_frame.shape[0]))

                output_frame = self.generator.blend_frames(real_frame, fake_frame, ratio)
            else:
                output_frame = real_frame

            # (7) virtual cam output
            if self.bridge is not None:
                self.bridge.send(output_frame)

            # (8) export state (서버가 가져갈 정보)
            with self._lock:
                self._state = {
                    "mode": self.mode,
                    "ratio": float(ratio),
                    "lockedFake": bool(self.locked_fake),
                    "pauseFake": bool(self.pause_fake_playback),
                    "forceReal": bool(self.force_real),
                    "reasons": list(reasons),
                    "timestamp": time.time(),
                    "reaction": reaction,  # 락 처음 걸릴 때만 값 들어감
                }

            # (9) fps limit (선택)
            if self.fps_limit:
                dt = time.time() - last_frame_time
                target_dt = 1.0 / float(self.fps_limit)
                if dt < target_dt:
                    time.sleep(target_dt - dt)
                last_frame_time = time.time()