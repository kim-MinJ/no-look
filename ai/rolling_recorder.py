# ai/rolling_recorder.py
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

import cv2


@dataclass
class Segment:
    path: str
    start_ts: float
    end_ts: float

def _make_writer(path: str, w: int, h: int, fps: float) -> cv2.VideoWriter:
    # ✅ Windows에서 제일 무난: mp4v (openh264 안 탐)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    if writer.isOpened():
        return writer

    # 그래도 안 열리면 컨테이너/코덱 문제라서 avi로 바꾸는게 안전
    raise RuntimeError("VideoWriter open failed. Try changing extension to .avi and codec to MJPG/XVID.")



class RollingRecorder:
    """
    - 실시간 프레임을 N초 단위(seg)로 잘라 mp4로 저장
    - 최근 rolling_seconds 만큼만 유지(오래된 seg는 삭제)
    - FAKE 시점엔 가장 오래된 seg부터 순서대로 재생(= 딜레이 영상)
    """

    def __init__(
        self,
        out_dir: str,
        width: int,
        height: int,
        fps: float,
        rolling_seconds: int = 120,        # ✅ 기본 2분
        segment_seconds: int = 10,
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
        self.recording_enabled = bool(enabled)
        if not self.recording_enabled:
            self._close_writer()

    def _open_new_segment(self, now_ts: float) -> None:
        self._close_writer()

        name = f"seg_{int(now_ts*1000)}.mp4"
        path = os.path.join(self.out_dir, name)

        self._writer = _make_writer(path, self.w, self.h, self.fps)
        self._seg_start_ts = now_ts
        self._seg_path = path

    def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
        self._writer = None

        # 세그 종료 처리(segments 큐에 등록)
        if self._seg_start_ts is not None and self._seg_path is not None:
            end_ts = time.time()
            self._segments.append(Segment(self._seg_path, self._seg_start_ts, end_ts))

        self._seg_start_ts = None
        self._seg_path = None

    def _cleanup_old(self, now_ts: float) -> None:
        # rolling_seconds보다 오래된 세그 삭제
        cutoff = now_ts - self.rolling_seconds
        while self._segments and self._segments[0].end_ts < cutoff:
            seg = self._segments.popleft()
            try:
                os.remove(seg.path)
            except Exception:
                pass

    def update(self, frame, now_ts: float) -> None:
        """
        REAL 모드에서 매 프레임 호출해서 버퍼를 유지.
        """
        if not self.recording_enabled:
            return

        if frame is None:
            return

        if frame.shape[1] != self.w or frame.shape[0] != self.h:
            frame = cv2.resize(frame, (self.w, self.h))

        if self._writer is None:
            self._open_new_segment(now_ts)

        # segment_seconds 경과하면 세그 교체
        if self._seg_start_ts is not None and (now_ts - self._seg_start_ts) >= self.segment_seconds:
            self._open_new_segment(now_ts)

        # write
        if self._writer is not None:
            self._writer.write(frame)

        self._cleanup_old(now_ts)

    def start_playback(self) -> None:
        """
        현재 보유중인 seg들을 순서대로 재생 시작(가장 오래된 것부터).
        """
        self.stop_playback()
        self._play_paths = [s.path for s in list(self._segments)]
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
        """
        playback 중 다음 프레임 반환. 없으면 None.
        """
        if self._play_cap is None:
            return None

        ret, frame = self._play_cap.read()
        if ret:
            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                frame = cv2.resize(frame, (self.w, self.h))
            return frame

        # 현재 세그 끝 → 다음 세그로
        try:
            self._play_cap.release()
        except Exception:
            pass
        self._play_cap = None

        self._play_index += 1
        if self._play_index >= len(self._play_paths):
            # 끝까지 갔으면 루프(자연스러운 반복)
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
