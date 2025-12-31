import os
import time
import threading
from typing import Any, Dict, Optional

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

    ✅ 추가:
    - 시작 후 5분 워밍업 녹화(로컬 mp4 저장)
    - 워밍업 동안 추적(미디어파이프) 완전 OFF
    - 워밍업이 끝나면, 방금 녹화한 영상으로 fake 소스 자동 교체
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
        self.assets_dir = os.path.join(base_dir, "assets")
        os.makedirs(self.assets_dir, exist_ok=True)

        # ✅ 워밍업(5분) 설정
        self.warmup_seconds = 300
        self.warmup_active = True
        self.warmup_end_ts = time.time() + self.warmup_seconds
        self.warmup_video_path = os.path.join(self.assets_dir, "warmup_5min.mp4")
        self._warmup_writer: Optional[cv2.VideoWriter] = None
        self._warmup_writer_ready = False
        self.fake_source = "sample"  # "sample" | "warmup"

        # 기존 fake 샘플 경로
        self.fake_video_path = fake_video_path or os.path.join(self.assets_dir, "fake_sample.mp4")

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
            "timestamp": time.time(),
            "reaction": None,
            # ✅ 워밍업 상태 추가
            "warmup": True,
            "warmupRemainingSec": self.warmup_seconds,
            "trackingEnabled": False,
            "fakeSource": self.fake_source,
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

        try:
            if self._warmup_writer is not None:
                self._warmup_writer.release()
        except Exception:
            pass
        self._warmup_writer = None
        self._warmup_writer_ready = False

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self.bridge = None

    # ---------- warmup helpers ----------
    def _init_warmup_writer(self, width: int, height: int, fps: float) -> None:
        """
        ✅ mp4로 5분 녹화 저장 (warmup_5min.mp4)
        """
        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(self.warmup_video_path, fourcc, float(fps), (int(width), int(height)))
            if not writer.isOpened():
                print("[Warmup] VideoWriter open failed:", self.warmup_video_path)
                self._warmup_writer = None
                self._warmup_writer_ready = False
                return
            self._warmup_writer = writer
            self._warmup_writer_ready = True
            print("[Warmup] Recording to:", self.warmup_video_path)
        except Exception as e:
            print("[Warmup] Writer init error:", e)
            self._warmup_writer = None
            self._warmup_writer_ready = False

    def _finish_warmup(self) -> None:
        """
        ✅ 5분 끝: writer 닫고, generator fake 소스를 warmup 영상으로 교체
        """
        try:
            if self._warmup_writer is not None:
                self._warmup_writer.release()
        except Exception:
            pass

        self._warmup_writer = None
        self._warmup_writer_ready = False

        self.warmup_active = False
        self.fake_source = "warmup"

        # 방금 만든 warmup 영상으로 fake 소스 교체
        self.generator.reload(self.warmup_video_path)
        print("[Warmup] Done. Fake source switched to warmup_5min.mp4")

    # ---------- internal loop ----------
    def _run(self) -> None:
        self.cap = cv2.VideoCapture(self.webcam_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"Webcam open failed: {self.webcam_id}")

        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # fps 결정 (limit 우선)
        cap_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if not cap_fps or cap_fps <= 1:
            cap_fps = 30.0
        fps = float(self.fps_limit) if self.fps_limit else float(cap_fps)

        # VirtualCam init
        self.bridge = VirtualCam(width, height, fps=int(fps) if fps else 30)

        # ✅ warmup 녹화 writer 준비
        self._init_warmup_writer(width, height, fps if fps else 30.0)

        last_frame_time = time.time()

        while not self._stop_event.is_set():
            ret, real_frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            now = time.time()

            # ======================================================
            # ✅ WARMUP MODE: 5분 동안 "녹화만" + "추적 OFF"
            # ======================================================
            if self.warmup_active:
                remaining = max(0, int(self.warmup_end_ts - now))

                # 녹화
                if self._warmup_writer_ready and self._warmup_writer is not None:
                    try:
                        self._warmup_writer.write(real_frame)
                    except Exception:
                        pass

                # warmup 종료 체크
                if now >= self.warmup_end_ts:
                    self._finish_warmup()
                    remaining = 0

                # 워밍업 중엔 무조건 REAL 송출(추적/락/전환 없음)
                if self.bridge is not None:
                    self.bridge.send(real_frame)

                with self._lock:
                    self.mode = "REAL"
                    self.locked_fake = False
                    self._state = {
                        "mode": "REAL",
                        "ratio": 0.0,
                        "lockedFake": False,
                        "pauseFake": bool(self.pause_fake_playback),
                        "forceReal": bool(self.force_real),
                        "reasons": ["WARMUP_RECORDING"],
                        "timestamp": time.time(),
                        "reaction": None,
                        "warmup": True,
                        "warmupRemainingSec": remaining,
                        "trackingEnabled": False,
                        "fakeSource": self.fake_source,
                    }

                # fps limit (선택)
                if self.fps_limit:
                    dt = time.time() - last_frame_time
                    target_dt = 1.0 / float(self.fps_limit)
                    if dt < target_dt:
                        time.sleep(target_dt - dt)
                    last_frame_time = time.time()

                continue

            # ======================================================
            # ✅ NORMAL MODE: warmup 이후부터 기존 추적 로직
            # ======================================================
            is_distracted, reasons = self.detector.is_distracted(real_frame)

            with self._lock:
                force_real = self.force_real
                pause_fake = self.pause_fake_playback

                # latch(한번 딴짓이면 FAKE 고정) - force_real이면 latch 무시
                reaction = None
                if (not force_real) and is_distracted and (not self.locked_fake):
                    self.locked_fake = True
                    reaction = self.bot.get_reaction()

                # target mode
                target_mode = "REAL" if force_real else ("FAKE" if self.locked_fake else "REAL")

                # transition start
                if target_mode != self.mode:
                    self.mode = target_mode
                    self.trans_start = time.time()

                # ratio
                elapsed = time.time() - self.trans_start
                progress = min(elapsed / self.transition_time, 1.0)
                ratio = progress if self.mode == "FAKE" else (1.0 - progress)

            # generate fake frame (pause면 마지막 프레임 고정)
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

            # virtual cam output
            if self.bridge is not None:
                self.bridge.send(output_frame)

            # export state
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
                    "warmup": False,
                    "warmupRemainingSec": 0,
                    "trackingEnabled": True,
                    "fakeSource": self.fake_source,
                }

            # fps limit (선택)
            if self.fps_limit:
                dt = time.time() - last_frame_time
                target_dt = 1.0 / float(self.fps_limit)
                if dt < target_dt:
                    time.sleep(target_dt - dt)
                last_frame_time = time.time()
