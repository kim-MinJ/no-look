# ai/engine.py
import os
import sys
import time
import threading
from typing import Any, Dict, Optional

import cv2

from detector import DistractionDetector
from generator import StreamGenerator
from bridge import VirtualCam
from bot import MeetingBot
from rolling_recorder import RollingRecorder
from scene_transition import TransitionManager


class NoLookEngine:
    """
    - 웹캠 점유(OpenCV)
    - ✅ "첫 접속" 시점에 warmup 녹화 시작 (30초)
    - warmup 동안은 "녹화만" 하고 추적 OFF
    - 이후 디텍터 ON
    - REAL에서는 rolling_seconds 만큼 롤링 저장
    - FAKE로 전환되면 롤링 버퍼를 재생(딜레이 영상)
    """

    def __init__(
        self,
        webcam_id: int = 0,
        fake_video_path: Optional[str] = None,
        transition_time: float = 0.5,
        fps_limit: Optional[float] = None,

        # ✅ 요구사항: 처음 접속 시 30초 녹화
        warmup_seconds: int = 30,
        rolling_seconds: int = 10,
        rolling_segment_seconds: int = 2,
    ):
        self.webcam_id = webcam_id
        self.transition_time = float(transition_time)
        self.fps_limit = fps_limit

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.fake_video_path = fake_video_path or os.path.join(base_dir, "assets", "fake_sample.mp4")

        self.runtime_dir = os.path.join(base_dir, "runtime")
        self.rolling_dir = os.path.join(self.runtime_dir, "rolling")
        os.makedirs(self.rolling_dir, exist_ok=True)

        self.warmup_seconds = int(warmup_seconds)
        self.rolling_seconds = int(rolling_seconds)
        self.rolling_segment_seconds = int(rolling_segment_seconds)

        self.detector = DistractionDetector()
        self.generator = StreamGenerator(self.fake_video_path)
        self.transition_manager = TransitionManager(base_dir)
        self.bot = MeetingBot()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.cap: Optional[cv2.VideoCapture] = None
        self.bridge: Optional[VirtualCam] = None
        self.rolling: Optional[RollingRecorder] = None

        self.mode = "REAL"
        self.trans_start = time.time()

        self.locked_fake = False
        self.pause_fake_playback = False
        self.force_real = False

        self.last_fake_frame = None
        self.transition_effect = "natural_lag"

        # ✅ 핵심: 세션 시작(=첫 접속) 전에는 warmup도, 추적도 안 함
        self.session_active = False

        self._warmup_start = 0.0
        self._warmup_end = 0.0
        self._warming_up = False

        # ✅ reset_lock 직후 바로 다시 락 걸리는 거 방지 (2초 쿨다운)
        self._cooldown_until = 0.0

        self._state: Dict[str, Any] = {
            "sessionActive": False,
            "mode": "REAL",
            "ratio": 0.0,
            "lockedFake": False,
            "pauseFake": False,
            "forceReal": False,
            "reasons": [],
            "timestamp": time.time(),
            "reaction": None,
            "notice": None,
            "warmingUp": False,
            "warmupTotalSec": self.warmup_seconds,
            "warmupRemainingSec": 0,
            "transitionEffect": self.transition_effect,
        }

    # ---------- session ----------
    def start_session_if_needed(self) -> None:
        """✅ 첫 접속 시 warmup을 시작한다."""
        with self._lock:
            if self.session_active:
                return

            self.session_active = True
            self.locked_fake = False
            self.mode = "REAL"
            self.trans_start = time.time()

            now = time.time()
            self._warmup_start = now
            self._warmup_end = now + self.warmup_seconds
            self._warming_up = True

            self._state = {
                **self._state,
                "sessionActive": True,
                "mode": "REAL",
                "ratio": 0.0,
                "lockedFake": False,
                "reasons": ["WARMUP_RECORDING"],
                "timestamp": now,
                "notice": None,
                "warmingUp": True,
                "warmupTotalSec": self.warmup_seconds,
                "warmupRemainingSec": self.warmup_seconds,
            }

    # ---------- controls ----------
    def set_pause_fake(self, value: bool) -> None:
        with self._lock:
            self.pause_fake_playback = bool(value)

    def set_force_real(self, value: bool) -> None:
        with self._lock:
            self.force_real = bool(value)
            # 강제 REAL이면 즉시 REAL로
            if self.force_real and self.mode != "REAL":
                self.mode = "REAL"
                self.trans_start = time.time()

    def set_transition_effect(self, effect_name: str) -> None:
        with self._lock:
            self.transition_effect = effect_name

    def reset_lock(self) -> None:
        with self._lock:
            self.locked_fake = False
            self.mode = "REAL"
            self.trans_start = time.time()
            # ✅ reset 누른 직후 2초는 탐지 무시 (다시 바로 락 걸리는 체감 방지)
            self._cooldown_until = time.time() + 2.0

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

        if self.rolling is not None:
            try:
                self.rolling.set_recording_enabled(False)
                self.rolling.stop_playback()
            except Exception:
                pass
            self.rolling = None

        if self.bridge is not None:
            try:
                self.bridge.close()
            except Exception:
                pass
            self.bridge = None

    # ---------- internal ----------
    def _open_capture(self) -> cv2.VideoCapture:
        if sys.platform == "darwin":
            return cv2.VideoCapture(self.webcam_id, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(self.webcam_id)

    def _run(self) -> None:
        self.cap = self._open_capture()
        if not self.cap.isOpened():
            raise RuntimeError(f"Webcam open failed: {self.webcam_id}")

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        fps = float(self.cap.get(cv2.CAP_PROP_FPS)) or 30.0

        self.bridge = VirtualCam(width, height, fps=fps)

        self.rolling = RollingRecorder(
            out_dir=self.rolling_dir,
            width=width,
            height=height,
            fps=fps,
            rolling_seconds=self.rolling_seconds,
            segment_seconds=self.rolling_segment_seconds,
        )

        last_frame_time = time.time()

        while not self._stop_event.is_set():
            ret, real_frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            now = time.time()

            # ✅ 세션 시작 전(=첫 접속 전)에는 그냥 REAL 출력만
            if not self.session_active:
                if self.rolling is not None:
                    self.rolling.set_recording_enabled(False)

                if self.bridge is not None:
                    self.bridge.send(real_frame)

                with self._lock:
                    self._state = {
                        **self._state,
                        "sessionActive": False,
                        "mode": "REAL",
                        "ratio": 0.0,
                        "lockedFake": bool(self.locked_fake),
                        "pauseFake": bool(self.pause_fake_playback),
                        "forceReal": bool(self.force_real),
                        "reasons": ["WAITING_FIRST_CONNECT"],
                        "timestamp": now,
                        "notice": None,
                        "warmingUp": False,
                        "warmupTotalSec": self.warmup_seconds,
                        "warmupRemainingSec": 0,
                        "transitionEffect": self.transition_effect,
                    }

                # fps limit
                if self.fps_limit:
                    dt = time.time() - last_frame_time
                    target_dt = 1.0 / float(self.fps_limit)
                    if dt < target_dt:
                        time.sleep(target_dt - dt)
                    last_frame_time = time.time()
                continue

            # ✅ warmup: 추적 OFF + 롤링 저장만
            notice = None
            if self._warming_up:
                remaining = max(0, int(self._warmup_end - now))

                if self.rolling is not None:
                    self.rolling.set_recording_enabled(True)
                    self.rolling.update(real_frame, now)

                if now >= self._warmup_end:
                    self._warming_up = False
                    notice = "✅ 녹화 완료! 이제 추적 시작합니다."

                if self.bridge is not None:
                    self.bridge.send(real_frame)

                with self._lock:
                    self._state = {
                        **self._state,
                        "sessionActive": True,
                        "mode": "REAL",
                        "ratio": 0.0,
                        "lockedFake": bool(self.locked_fake),
                        "pauseFake": bool(self.pause_fake_playback),
                        "forceReal": bool(self.force_real),
                        "reasons": ["WARMUP_RECORDING"],
                        "timestamp": now,
                        "notice": notice,
                        "warmingUp": True,
                        "warmupTotalSec": self.warmup_seconds,
                        "warmupRemainingSec": remaining,
                        "transitionEffect": self.transition_effect,
                    }

                if self.fps_limit:
                    dt = time.time() - last_frame_time
                    target_dt = 1.0 / float(self.fps_limit)
                    if dt < target_dt:
                        time.sleep(target_dt - dt)
                    last_frame_time = time.time()
                continue

            # ✅ 추적 ON
            is_distracted, reasons = self.detector.is_distracted(real_frame)

            # ✅ reset 직후 쿨다운
            if now < self._cooldown_until:
                is_distracted = False
                reasons = ["COOLDOWN_AFTER_RESET"]

            with self._lock:
                force_real = self.force_real
                pause_fake = self.pause_fake_playback

                reaction = None
                if (not force_real) and is_distracted and (not self.locked_fake):
                    self.locked_fake = True
                    reaction = self.bot.get_reaction()

                target_mode = "REAL" if force_real else ("FAKE" if self.locked_fake else "REAL")

                mode_changed = target_mode != self.mode
                if mode_changed:
                    self.mode = target_mode
                    self.trans_start = time.time()

                    if self.mode == "FAKE":
                        self.transition_manager.start(effect_name=self.transition_effect)
                        if self.rolling is not None:
                            self.rolling.start_playback()

                    if self.mode == "REAL":
                        self.transition_manager.stop()
                        if self.rolling is not None:
                            self.rolling.stop_playback()

                elapsed = time.time() - self.trans_start
                progress = min(elapsed / self.transition_time, 1.0)
                ratio = progress if self.mode == "FAKE" else (1.0 - progress)

            # ✅ REAL이면 롤링 계속 저장
            if self.rolling is not None:
                self.rolling.set_recording_enabled(self.mode == "REAL")
                if self.mode == "REAL":
                    self.rolling.update(real_frame, now)

            # ✅ FAKE 프레임 생성
            if self.mode == "FAKE":
                fake_frame = None

                if self.rolling is not None:
                    if pause_fake and (self.last_fake_frame is not None):
                        fake_frame = self.last_fake_frame
                    else:
                        fake_frame = self.rolling.read_playback_frame()

                if fake_frame is None:
                    fake_frame = self.generator.get_fake_frame()

                # ✅ [Fix] 롤링/제너레이터 모두 프레임 반환 실패 시,
                # 바로 리얼타임(real_frame)을 보여주면 영상 전환부에서 깜빡임(Glitch) 발생.
                # 따라서 이전에 출력했던 FAKE 프레임을 우선 재사용한다.
                if fake_frame is None and self.last_fake_frame is not None:
                    fake_frame = self.last_fake_frame

                if fake_frame is None:
                    fake_frame = real_frame.copy()

                if fake_frame.shape[:2] != real_frame.shape[:2]:
                    fake_frame = cv2.resize(fake_frame, (real_frame.shape[1], real_frame.shape[0]))

                if not pause_fake:
                    self.last_fake_frame = fake_frame

                output_frame = self.generator.blend_frames(real_frame, fake_frame, ratio)

                effect_frame = self.transition_manager.get_frame(real_frame, target_frame=fake_frame)
                if effect_frame is not None:
                    output_frame = effect_frame
            else:
                output_frame = real_frame

            if self.bridge is not None:
                self.bridge.send(output_frame)

            with self._lock:
                self._state = {
                    **self._state,
                    "sessionActive": True,
                    "mode": self.mode,
                    "ratio": float(ratio),
                    "lockedFake": bool(self.locked_fake),
                    "pauseFake": bool(self.pause_fake_playback),
                    "forceReal": bool(self.force_real),
                    "transitionEffect": self.transition_effect,
                    "reasons": list(reasons),
                    "timestamp": now,
                    "reaction": reaction,
                    "notice": None,
                    "warmingUp": False,
                    "warmupTotalSec": self.warmup_seconds,
                    "warmupRemainingSec": 0,
                }

            if self.fps_limit:
                dt = time.time() - last_frame_time
                target_dt = 1.0 / float(self.fps_limit)
                if dt < target_dt:
                    time.sleep(target_dt - dt)
                last_frame_time = time.time()
