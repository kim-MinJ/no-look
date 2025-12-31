import os
from typing import List, Optional

import cv2


class StreamGenerator:
    def __init__(self, video_path: str):
        self.base_video_path = video_path
        self.playlist: List[str] = [video_path]
        self.play_idx: int = 0
        self.cap: Optional[cv2.VideoCapture] = None

        self._open_current()

    def set_single_video(self, video_path: str) -> None:
        """기본 fake_sample.mp4 같은 단일 파일로 되돌릴 때"""
        self.base_video_path = video_path
        self.set_playlist([video_path])

    def set_playlist(self, paths: List[str], start_from_end: bool = False) -> None:
        """
        여러 영상 조각(오래된→최신)을 순서대로 재생.
        start_from_end=True면 마지막쪽부터 시작(더 '지금'처럼 보임)
        """
        cleaned = [p for p in paths if p and os.path.exists(p)]
        if not cleaned:
            cleaned = [self.base_video_path]

        self._release()
        self.playlist = cleaned
        if start_from_end:
            self.play_idx = max(0, len(self.playlist) - 2)  # 최근 구간부터 시작(너무 과거로 튀는 것 방지)
        else:
            self.play_idx = 0
        self._open_current()

    def get_fake_frame(self):
        """Returns the next frame from the current playlist (loop)."""
        if not self._ensure_open():
            return None

        ret, frame = self.cap.read()
        if ret:
            return frame

        # 현재 파일 끝 -> 다음 파일로
        for _ in range(len(self.playlist) + 1):
            self._advance()
            if not self._ensure_open():
                return None
            ret, frame = self.cap.read()
            if ret:
                return frame

        return None

    def blend_frames(self, real, fake, ratio: float):
        """
        Ratio 0.0 -> 100% Real
        Ratio 1.0 -> 100% Fake
        """
        if real is None or fake is None:
            return real if real is not None else fake

        if real.shape != fake.shape:
            fake = cv2.resize(fake, (real.shape[1], real.shape[0]))

        return cv2.addWeighted(real, 1.0 - ratio, fake, ratio, 0.0)

    # ---------------- internal ----------------
    def _advance(self):
        self._release()
        if not self.playlist:
            self.playlist = [self.base_video_path]
        self.play_idx = (self.play_idx + 1) % len(self.playlist)

    def _open_current(self):
        if not self.playlist:
            return
        path = self.playlist[self.play_idx]
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            print(f"[StreamGenerator] Warning: Failed to load video: {path}")

    def _release(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None

    def _ensure_open(self) -> bool:
        if self.cap is None or (not self.cap.isOpened()):
            self._open_current()
        return self.cap is not None and self.cap.isOpened()
