import cv2
import time
import numpy as np
import threading
from typing import Optional

class VideoState:
    class Mode:
        REAL = 0
        FAKE = 1

    def __init__(self):
        self.target_mode = self.Mode.REAL
        self.alpha = 0.0  # 0.0 = Real, 1.0 = Fake
        self.last_update = time.time()
        self.fade_duration = 0.3  # seconds

    def set_target(self, mode: int, fade_ms: float = 300):
        self.target_mode = mode
        self.fade_duration = fade_ms / 1000.0

    def update_alpha(self):
        now = time.time()
        dt = now - self.last_update
        self.last_update = now

        target_alpha = 1.0 if self.target_mode == self.Mode.FAKE else 0.0
        
        if abs(self.alpha - target_alpha) < 0.001:
            self.alpha = target_alpha
            return

        step = dt / self.fade_duration
        if self.alpha < target_alpha:
            self.alpha = min(target_alpha, self.alpha + step)
        else:
            self.alpha = max(target_alpha, self.alpha - step)

class LightingMatcher:
    def __init__(self):
        self.avg_diff = 0.0
        self.smoothing_factor = 0.2
        self.calc_interval = 3
        self.frame_counter = 0

    def match(self, real_frame, fake_frame):
        self.frame_counter += 1
        
        if self.frame_counter % self.calc_interval == 0:
            self._calculate_diff(real_frame, fake_frame)
            
        self._apply_adjustment(fake_frame)

    def _calculate_diff(self, real, fake):
        # Downsample for performance (1/4 size)
        h, w = real.shape[:2]
        small_size = (max(1, w // 4), max(1, h // 4))
        
        d_real = cv2.resize(real, small_size)
        d_fake = cv2.resize(fake, small_size)
        
        real_lab = cv2.cvtColor(d_real, cv2.COLOR_BGR2Lab)
        fake_lab = cv2.cvtColor(d_fake, cv2.COLOR_BGR2Lab)
        
        real_l = cv2.mean(real_lab)[0]
        fake_l = cv2.mean(fake_lab)[0]
        
        current_diff = real_l - fake_l
        self.avg_diff = (self.smoothing_factor * current_diff) + \
                        (1.0 - self.smoothing_factor) * self.avg_diff

    def _apply_adjustment(self, fake):
        fake_lab = cv2.cvtColor(fake, cv2.COLOR_BGR2Lab)
        l, a, b = cv2.split(fake_lab)
        
        # Apply brightness diff
        l = cv2.add(l, self.avg_diff)
        
        fake_lab = cv2.merge([l, a, b])
        cv2.cvtColor(fake_lab, cv2.COLOR_Lab2BGR, dst=fake)

class VideoEngine:
    def __init__(self, asset_path="../ai/assets/fake_sample.mp4"):
        self.state = VideoState()
        self.matcher = LightingMatcher()
        
        self.real_cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.fake_video = cv2.VideoCapture(asset_path)
        
        self.running = True
        self.latest_frame = None
        self.lock = threading.Lock()
        
        # Start processing thread
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()

    def get_frame_jpeg(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.latest_frame)
            return jpeg.tobytes() if ret else None

    def set_mode(self, mode_str: str):
        if mode_str.lower() == "fake":
            self.state.set_target(VideoState.Mode.FAKE)
        else:
            self.state.set_target(VideoState.Mode.REAL)

    def _process_loop(self):
        while self.running:
            # 1. Read Real
            ret_real, real_frame = self.real_cam.read()
            if not ret_real:
                time.sleep(0.01)
                continue

            # 2. Read Fake (Loop)
            ret_fake, fake_frame = self.fake_video.read()
            if not ret_fake:
                self.fake_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret_fake, fake_frame = self.fake_video.read()
                if not ret_fake:
                    continue
            
            # Resize fake to match real
            fake_frame = cv2.resize(fake_frame, (real_frame.shape[1], real_frame.shape[0]))

            # 3. Match Lighting
            self.matcher.match(real_frame, fake_frame)

            # 4. Blend
            self.state.update_alpha()
            alpha = self.state.alpha
            
            output = cv2.addWeighted(real_frame, 1.0 - alpha, fake_frame, alpha, 0.0)

            with self.lock:
                self.latest_frame = output
            
            time.sleep(0.01) # Approx 60-100 FPS cap

    def stop(self):
        self.running = False
        self.real_cam.release()
        self.fake_video.release()
