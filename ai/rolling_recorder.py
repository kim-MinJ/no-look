import os
import time
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

import cv2


@dataclass
class Segment:
    # 엔진(FAKE 재생)에서 쓸 원본 경로 (OpenCV가 잘 읽는 포맷)
    src_path: str
    # 웹에서 재생할 H.264 mp4 경로(없을 수 있음)
    web_path: Optional[str]
    start_ts: float
    end_ts: float


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_web_mp4_h264(src_path: str) -> Optional[str]:
    """
    브라우저 호환 목표:
    - H.264(avc1) + yuv420p + faststart
    - 세그먼트가 짧으면 동기 변환해도 보통 OK
    """
    if not _has_ffmpeg():
        return None

    dst_path = os.path.splitext(src_path)[0] + "_web.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", src_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-profile:v", "baseline",
        "-preset", "veryfast",
        "-crf", "23",
        "-movflags", "+faststart",
        dst_path,
    ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        # 변환 파일이 실제로 열리는지 간단 체크(깨진 mp4 방지)
        cap = cv2.VideoCapture(dst_path)
        ok = cap.isOpened()
        cap.release()
        return dst_path if ok else None
    except Exception:
        return None


def _make_writer_mjpg_avi(base_path: str, w: int, h: int, fps: float) -> tuple[cv2.VideoWriter, str]:
    """
    ✅ 녹화 안정성 최우선: AVI + MJPG
    (OpenCV가 거의 모든 환경에서 잘 쓰고 잘 읽음)
    """
    root, _ = os.path.splitext(base_path)
    path = root + ".avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter(MJPG/AVI) open failed.")
    return writer, path


class RollingRecorder:
    """
    - REAL 모드에서 최근 N초(rolling_seconds) 분량을 세그먼트로 저장
    - FAKE 모드에선 저장된 세그먼트를 오래된 것부터 재생(딜레이 영상)
    - 웹 재생용으로는 세그 종료 시 H.264 mp4로 변환본을 추가 생성(web_path)
    """

    def __init__(
        self,
        out_dir: str,
        width: int,
        height: int,
        fps: float,
        rolling_seconds: int = 10,
        segment_seconds: int = 2,
    ):
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

        self.w = int(width)
        self.h = int(height)
        self.fps = float(fps) if fps and fps > 0 else 30.0

        self.rolling_seconds = int(rolling_seconds)
        self.segment_seconds = int(segment_seconds)

        self._segments: Deque[Segment] = deque()

        self._writer: Optional[cv2.VideoWriter] = None
        self._seg_start_ts: Optional[float] = None
        self._seg_path: Optional[str] = None

        # playback
        self._play_paths: List[str] = []
        self._play_index: int = 0
        self._play_cap: Optional[cv2.VideoCapture] = None

        self.recording_enabled: bool = True

    def set_recording_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.recording_enabled == enabled:
            return
        self.recording_enabled = enabled
        if not self.recording_enabled:
            self._close_writer()

    def _open_new_segment(self, now_ts: float) -> None:
        self._close_writer()

        name = f"seg_{int(now_ts*1000)}.tmp"
        base_path = os.path.join(self.out_dir, name)

        self._writer, self._seg_path = _make_writer_mjpg_avi(base_path, self.w, self.h, self.fps)
        self._seg_start_ts = now_ts

    def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
        self._writer = None

        if self._seg_start_ts is not None and self._seg_path is not None:
            end_ts = time.time()

            # ✅ 웹용 H.264 mp4 생성(가능하면)
            web_path = _convert_to_web_mp4_h264(self._seg_path)

            self._segments.append(Segment(
                src_path=self._seg_path,
                web_path=web_path,
                start_ts=self._seg_start_ts,
                end_ts=end_ts
            ))

        self._seg_start_ts = None
        self._seg_path = None

    def _cleanup_old(self, now_ts: float) -> None:
        cutoff = now_ts - self.rolling_seconds
        while self._segments and self._segments[0].end_ts < cutoff:
            seg = self._segments.popleft()
            for p in [seg.src_path, seg.web_path]:
                if not p:
                    continue
                try:
                    os.remove(p)
                except Exception:
                    pass

    def update(self, frame, now_ts: float) -> None:
        if not self.recording_enabled or frame is None:
            return

        if frame.shape[1] != self.w or frame.shape[0] != self.h:
            frame = cv2.resize(frame, (self.w, self.h))

        if self._writer is None:
            self._open_new_segment(now_ts)

        if self._seg_start_ts is not None and (now_ts - self._seg_start_ts) >= self.segment_seconds:
            self._open_new_segment(now_ts)

        if self._writer is not None:
            self._writer.write(frame)

        self._cleanup_old(now_ts)

    # ---------- playback ----------
    def start_playback(self) -> None:
        self.stop_playback()
        # ✅ 엔진 재생은 OpenCV가 잘 읽는 src_path 사용
        self._play_paths = [s.src_path for s in list(self._segments)]
        self._play_index = 0
        self._open_play_cap()

    def _open_play_cap(self) -> None:
        if self._play_index >= len(self._play_paths):
            self._play_cap = None
            return

        path = self._play_paths[self._play_index]
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self._play_index += 1
            self._open_play_cap()
            return

        self._play_cap = cap

    def read_playback_frame(self):
        if self._play_cap is None:
            return None

        ret, frame = self._play_cap.read()
        if ret:
            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                frame = cv2.resize(frame, (self.w, self.h))
            return frame

        try:
            self._play_cap.release()
        except Exception:
            pass
        self._play_cap = None

        self._play_index += 1
        if self._play_index >= len(self._play_paths):
            self._play_index = 0

        self._open_play_cap()
        return None

    def stop_playback(self) -> None:
        if self._play_cap is not None:
            try:
                self._play_cap.release()
            except Exception:
                pass
        self._play_cap = None
        self._play_paths = []
        self._play_index = 0

    # --- (옵션) 웹에 뿌릴 세그 목록 필요하면 이거 쓰면 됨 ---
    def list_web_paths(self) -> List[str]:
        return [s.web_path for s in self._segments if s.web_path]
