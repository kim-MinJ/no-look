import os
import time
import threading
from typing import Any, Dict, Optional

import cv2

from detector import DistractionDetector
from generator import StreamGenerator
from bridge import VirtualCam
from bot import MeetingBot
from rolling_recorder import RollingRecorder


class NoLookEngine:
    """
    - 웹캠을 단독 점유 (OpenCV)
    - detector로 상태 판단
    - RollingRecorder로 최근 N분 영상 조각을 계속 저장(롤링)
    - 딴짓 감지 시, 최근 영상 조각 playlist로 generator 재생
    - VirtualCam으로 출력
    - 최신 상태(state)를 서버가 가져갈 수 있게 제공
    """

    def __init__(
        self,
        webcam_id: int = 0,
        fake_video_path: Optional[str] = None,
        transition_time: float = 0.5,
        fps_limit: Optional[float] = None,
        # ✅ rolling config
        roll_keep_seconds: float = 300.0,      # 5분 유지
        roll_segment_seconds: float = 10.0,    # 10초 조각
        roll_trigger_window: float = 60.0,     # 딴짓 시 최근 60초 재생(더 자연스러움)
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

        # rolling recorder
        self.roll_keep_seconds = float(roll_keep_seconds)
        self.roll_segment_seconds = float(roll_segment_seconds)
        self.roll_trigger_window = float(roll_trigger_window)

        self.roll_dir = os.path.join(base_dir, "assets", "rolling")
        os.makedirs(self.roll_dir, exist_ok=True)

        self.rolling: Optional[RollingRecorder] = None

        # runtime
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.cap: Optional[cv2.VideoCapture] = None
        self.bridge: Optional[VirtualCam] = None

        # state machine
        self.mode = "REAL"
        self.trans_start = time.time()

        # latches / controls
        self.locked_fake = False
        self.pause_fake_playback = False
        self.force_real = False

        self.last_fake_frame = None  # pause용

        self._state: Dict[str, Any] = {
            "mode": "REAL",
            "ratio": 0.0,
            "lockedFake": False,
            "pauseFake": False,
            "forceReal": False,
            "reasons": [],
            "timestamp": time.time(),
            "reaction": None,
            "fakeSource": "sample",  # sample | rolling
        }

    # ---------- public control API ----------
    def set_pause_fake(self, value: bool) -> None:
        with self._lock:
            self.pause_fake_playback = bool(value)

    def set_force_real(self, value: bool) -> None:
        with self._lock:
            self.force_real = bool(value)
            if self.force_real:
                if self.mode != "REAL":
                    self.mode = "REAL"
                    self.trans_start = time.time()

    def reset_lock(self) -> None:
        with self._lock:
            self.locked_fake = False
            # generator 원복
            self.generator.set_single_video(self.fake_video_path)
            # 롤링 녹화 재개
            if self.rolling:
                self.rolling.resume()

            if self.mode != "REAL":
                self.mode = "REAL"
                self.trans_start = time.time()

    def get_state(self) -> Dict[str, Any]:
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

        self.bridge = None

        if self.rolling:
            try:
                self.rolling.pause()
            except Exception:
                pass

    # ---------- internal loop ----------
    def _run(self) -> None:
        self.cap = cv2.VideoCapture(self.webcam_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Webcam open failed: {self.webcam_id}")

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

        # fps 계산 (CAP_PROP_FPS가 0인 경우 많아서 fallback)
        cam_fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        if not cam_fps or cam_fps <= 1:
            cam_fps = float(self.fps_limit) if self.fps_limit else 30.0

        self.bridge = VirtualCam(width, height, fps=int(cam_fps))

        # ✅ rolling recorder init
        self.rolling = RollingRecorder(
            out_dir=self.roll_dir,
            segment_seconds=self.roll_segment_seconds,
            keep_seconds=self.roll_keep_seconds,
            fourcc="mp4v",
            ext=".mp4",
        )
        self.rolling.configure(width, height, cam_fps)

        last_frame_time = time.time()

        while not self._stop_event.is_set():
            ret, real_frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # ✅ (0) rolling record (FAKE 락 걸려서 FAKE 재생 중이면 굳이 녹화 멈춰도 됨)
            with self._lock:
                _locked = self.locked_fake
                _force_real = self.force_real
            if self.rolling and (not _locked or _force_real):
                self.rolling.write(real_frame)
            elif self.rolling and _locked and (not _force_real):
                # 락 걸려서 FAKE로 갈 때는 파일 삭제/충돌 이슈 피하려고 녹화 잠깐 멈춤
                self.rolling.pause()

            # (1) detect
            is_distracted, reasons = self.detector.is_distracted(real_frame)

            with self._lock:
                force_real = self.force_real
                pause_fake = self.pause_fake_playback

                reaction = None
                fake_source = self._state.get("fakeSource", "sample")

                # (2) latch: 첫 딴짓 순간에만 locked_fake + playlist 스냅샷
                if (not force_real) and is_distracted and (not self.locked_fake):
                    self.locked_fake = True
                    reaction = self.bot.get_reaction()

                    # ✅ 딴짓 순간: 최근 영상 조각을 generator에 장착
                    if self.rolling:
                        playlist = self.rolling.get_recent_playlist(window_seconds=self.roll_trigger_window)
                        if playlist:
                            self.generator.set_playlist(playlist, start_from_end=True)
                            fake_source = "rolling"
                        else:
                            # 아직 조각이 없으면 샘플로 fallback
                            self.generator.set_single_video(self.fake_video_path)
                            fake_source = "sample"

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

            # (6) fake frame
            if self.mode == "FAKE":
                if pause_fake and (self.last_fake_frame is not None):
                    fake_frame = self.last_fake_frame
                else:
                    fake_frame = self.generator.get_fake_frame()
                    if fake_frame is None:
                        fake_frame = real_frame.copy()
                    else:
                        self.last_fake_frame = fake_frame

                if fake_frame.shape[:2] != real_frame.shape[:2]:
                    fake_frame = cv2.resize(fake_frame, (real_frame.shape[1], real_frame.shape[0]))

                output_frame = self.generator.blend_frames(real_frame, fake_frame, ratio)
            else:
                output_frame = real_frame

            # (7) virtual cam output
            if self.bridge is not None:
                self.bridge.send(output_frame)

            # (8) export state
            with self._lock:
                self._state = {
                    "mode": self.mode,
                    "ratio": float(ratio),
                    "lockedFake": bool(self.locked_fake),
                    "pauseFake": bool(self.pause_fake_playback),
                    "forceReal": bool(self.force_real),
                    "reasons": list(reasons),
                    "timestamp": time.time(),
                    "reaction": reaction,
                    "fakeSource": fake_source,
                }

            # (9) fps limit
            if self.fps_limit:
                dt = time.time() - last_frame_time
                target_dt = 1.0 / float(self.fps_limit)
                if dt < target_dt:
                    time.sleep(target_dt - dt)
                last_frame_time = time.time()
