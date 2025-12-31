import os
import time
import math
from collections import deque
from typing import Deque, List, Optional, Tuple

import cv2


class RollingRecorder:
    """
    웹캠 프레임을 '짧은 영상 조각(segment)'으로 저장하면서 최신 keep_seconds 만큼만 유지.
    - segment_seconds: 조각 길이(초) (예: 10초)
    - keep_seconds: 유지할 전체 길이(초) (예: 300초 = 5분)
    """

    def __init__(
        self,
        out_dir: str,
        segment_seconds: float = 10.0,
        keep_seconds: float = 300.0,
        fourcc: str = "mp4v",
        ext: str = ".mp4",
    ):
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

        self.segment_seconds = float(segment_seconds)
        self.keep_seconds = float(keep_seconds)
        self.fourcc = fourcc
        self.ext = ext

        self._writer: Optional[cv2.VideoWriter] = None
        self._seg_start_ts: float = 0.0
        self._current_path: Optional[str] = None

        self._fps: float = 30.0
        self._size: Optional[Tuple[int, int]] = None  # (w, h)

        # deque of (path, start_ts)
        self._segments: Deque[Tuple[str, float]] = deque()

        self._paused: bool = False

    def configure(self, width: int, height: int, fps: float) -> None:
        self._size = (int(width), int(height))
        self._fps = float(fps) if fps and fps > 0 else 30.0

    def pause(self) -> None:
        self._paused = True
        self._close_writer()

    def resume(self) -> None:
        self._paused = False

    def clear(self) -> None:
        """모든 조각 파일 삭제"""
        self._close_writer()
        while self._segments:
            path, _ = self._segments.popleft()
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def write(self, frame) -> None:
        if self._paused:
            return
        if self._size is None:
            # configure 안 된 상태면 저장 불가
            return

        now = time.time()
        if (self._writer is None) or ((now - self._seg_start_ts) >= self.segment_seconds):
            self._rotate(now)

        if self._writer is not None:
            self._writer.write(frame)

    def get_playlist(self) -> List[str]:
        """현재 유지 중인 전체 조각(오래된→최신)"""
        return [p for (p, _) in list(self._segments) if os.path.exists(p)]

    def get_recent_playlist(self, window_seconds: float = 60.0) -> List[str]:
        """
        최근 window_seconds 만큼만 가져오기 (오래된→최신)
        - 딴짓 감지 순간 '최근 60초' 정도를 재생하면 훨씬 자연스러움
        """
        seg = max(self.segment_seconds, 1.0)
        need = int(math.ceil(window_seconds / seg)) + 1
        items = list(self._segments)[-need:] if need > 0 else list(self._segments)
        return [p for (p, _) in items if os.path.exists(p)]

    # ---------------- internal ----------------
    def _rotate(self, now: float) -> None:
        self._close_writer()

        fname = f"seg_{int(now * 1000)}{self.ext}"
        path = os.path.join(self.out_dir, fname)

        w, h = self._size
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc)
        writer = cv2.VideoWriter(path, fourcc, self._fps, (w, h))

        if not writer.isOpened():
            # mp4v가 안 열리면 avi + XVID로 바꾸면 대부분 해결됨
            # (근데 여기서 자동 변경하면 파일 확장자도 바꿔야 해서, 일단 에러만 출력)
            print(f"[RollingRecorder] VideoWriter open failed: {path} (fourcc={self.fourcc})")
            self._writer = None
            self._current_path = None
            return

        self._writer = writer
        self._seg_start_ts = now
        self._current_path = path
        self._segments.append((path, now))

        self._cleanup()

    def _cleanup(self) -> None:
        # 최신 keep_seconds 만큼만 유지하도록 조각 수 제한
        max_segments = int(math.ceil(self.keep_seconds / max(self.segment_seconds, 1.0))) + 1
        while len(self._segments) > max_segments:
            old_path, _ = self._segments.popleft()
            # 현재 writer가 쓰는 파일은 건드리지 않기
            if old_path == self._current_path:
                continue
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass

    def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
        self._writer = None
        self._current_path = None
