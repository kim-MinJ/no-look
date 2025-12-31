import cv2
import numpy as np
import time
import os

class TransitionManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.fade_video_path = os.path.join(base_dir, "assets", "fade.mp4")
        
        self.active = False
        self.start_time = 0.0
        
        # Stages duration
        self.FALL_DURATION = 0.3
        self.FREEZE_DURATION = 0.2
        self.FADE_DURATION = 2.0 # Default, will be adjusted by video length if possible
        
        self.last_effect_frame = None
        self.fade_cap = None
        
    def start(self, effect_name="falling"):
        """전효과 시작 (REAL -> FAKE 전환 시 호출)"""
        self.active = True
        self.start_time = time.time()
        self.last_effect_frame = None
        self.current_effect = effect_name
        
        # Fade 영상 로드
        if self.fade_cap is not None:
            self.fade_cap.release()
        self.fade_cap = cv2.VideoCapture(self.fade_video_path)
        
    def stop(self):
        """강제 중단 (사용자가 Lock 해제 시 등)"""
        self.active = False
        if self.fade_cap is not None:
            self.fade_cap.release()
            self.fade_cap = None

    def get_frame(self, real_frame, target_frame=None):
        """
        현재 진행 단계에 맞는 이펙트 프레임을 반환.
        target_frame: 이펙트가 끝날 때 보여줄 목표 프레임 (Fake 영상 프레임 등)
        """
        if not self.active:
            return None
            
        elapsed = time.time() - self.start_time
        
        if self.current_effect == "falling":
            return self._get_frame_falling(real_frame, elapsed)
        elif self.current_effect == "blackout":
            return self._get_frame_blackout(real_frame, elapsed, target_frame)
        
        return self._get_frame_falling(real_frame, elapsed) # Default

    def _get_frame_falling(self, real_frame, elapsed):
        # 1. Falling Effect (0 ~ 0.3s)
        if elapsed < self.FALL_DURATION:
            progress = elapsed / self.FALL_DURATION
            frame = self._dispatch_effect(real_frame, progress)
            self.last_effect_frame = frame
            return frame
            
        # 2. Freeze (0.3 ~ 0.5s)
        elif elapsed < (self.FALL_DURATION + self.FREEZE_DURATION):
            if self.last_effect_frame is not None:
                return self.last_effect_frame
            return real_frame
            
        # 3. Fade Video (0.5s ~ End)
        else:
            if self.fade_cap is None or not self.fade_cap.isOpened():
                self.active = False
                return None
                
            ret, frame = self.fade_cap.read()
            if not ret:
                self.active = False
                return None
                
            if real_frame is not None and frame.shape[:2] != real_frame.shape[:2]:
                h, w = real_frame.shape[:2]
                frame = cv2.resize(frame, (w, h))
                
            return frame

    def _get_frame_blackout(self, real_frame, elapsed, target_frame=None):
        """
        Blackout Effect Timing Logic
        1. Slow Down (0 ~ 0.3s): 프레임을 띄엄띄엄 업데이트하여 느려지는 느낌 연출
        2. Freeze (0.3 ~ 1.3s): 1초간 정지
        3. Black Screen (1.3 ~ 3.3s): 2초간 검은 화면
        4. Fade In (3.3s ~ 3.8s): 검은 화면에서 다음 화면(target_frame)으로 디졸브
        """
        SLOW_DURATION = 0.3
        FREEZE_DURATION = 1.0
        BLACK_DURATION = 2.0
        FADE_IN_DURATION = 0.5
        
        total_time = SLOW_DURATION + FREEZE_DURATION + BLACK_DURATION + FADE_IN_DURATION
        
        # 1. Slow Down
        if elapsed < SLOW_DURATION:
            if real_frame is None: return None
            stutter_interval = 0.1
            current_slot = int(elapsed / stutter_interval)
            
            if not hasattr(self, '_last_slot'):
                self._last_slot = -1
            if current_slot > self._last_slot:
                self.last_effect_frame = real_frame.copy()
                self._last_slot = current_slot
            if self.last_effect_frame is None:
                self.last_effect_frame = real_frame
            return self.last_effect_frame

        # 2. Freeze
        elif elapsed < (SLOW_DURATION + FREEZE_DURATION):
            if self.last_effect_frame is not None:
                return self.last_effect_frame
            return real_frame

        # 3. Black Screen
        elif elapsed < (SLOW_DURATION + FREEZE_DURATION + BLACK_DURATION):
            if real_frame is None: return None
            h, w = real_frame.shape[:2]
            return np.zeros((h, w, 3), dtype=np.uint8)
            
        # 4. Fade In (Black -> Target)
        elif elapsed < total_time:
            if real_frame is None: return None
            h, w = real_frame.shape[:2]
            black_frame = np.zeros((h, w, 3), dtype=np.uint8)
            
            # 진행도 (0.0 ~ 1.0)
            fade_progress = (elapsed - (SLOW_DURATION + FREEZE_DURATION + BLACK_DURATION)) / FADE_IN_DURATION
            fade_progress = max(0.0, min(1.0, fade_progress))
            
            # Target Frame (Fake)
            if target_frame is None:
                # 타겟이 없으면 그냥 블랙 유지하다가 끝냄
                return black_frame
                
            if target_frame.shape[:2] != (h, w):
                target_frame = cv2.resize(target_frame, (w, h))
                
            # Alpha Blend: Black * (1-p) + Target * p
            # Black is 0, so just Target * p?
            # cv2.addWeighted(src1, alpha, src2, beta, gamma)
            # src1=black, src2=target
            # alpha=1-p, beta=p
            
            # Simply: target * fade_progress (since black is 0)
            # But addWeighted is safer for types
            return cv2.addWeighted(black_frame, 1.0 - fade_progress, target_frame, fade_progress, 0.0)
            
        # 5. End
        else:
            self.active = False
            if hasattr(self, '_last_slot'): del self._last_slot
            return None

    def _dispatch_effect(self, frame, progress):
        """이펙트 이름에 따라 적절한 함수 호출"""
        if self.current_effect == "falling":
            return self._apply_motion_blur_falling(frame, progress)
        # 나중에 다른 효과 추가 가능
        # elif self.current_effect == "zoom_out":
        #     return self._apply_zoom_out(frame, progress)
        
        return self._apply_motion_blur_falling(frame, progress) # Default

    def _apply_motion_blur_falling(self, frame, progress):
        """
        [Effect: falling]
        화면 쓰러짐 효과 내부 로직 (Motion Blur + Vertical Stretch)
        사용자 요청: "상위 프레임이 늘어지는 느낌", "잔상", "색상이 앞으로 넘어지면서 잔상"
        """
        if frame is None: return None
        
        h, w = frame.shape[:2]
        progress = max(0.0, min(1.0, progress))
        
        # 0. 진행도가 낮을 땐 원본에 가까움 (하지만 급격히 빨라져야 함)
        # easeInExpo 느낌으로 progress 변형
        p_exp = progress ** 2
        
        # 1. Vertical Stretch (위로 늘어나는 느낌)
        # 이미지를 세로로 길게 늘림
        stretch_factor = 1.0 + (1.0 * p_exp) # 최대 2배 길이
        new_h = int(h * stretch_factor)
        
        # 크기 변경 (가로는 그대로, 세로는 늘림)
        stretched = cv2.resize(frame, (w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 2. Crop to original size
        # 하단을 고정하고 상단을 늘려보자.
        crop = stretched[0:h, :]
        
        # 3. Downward Shift (화면이 아래로 쏟아짐)
        shift_y = int(h * 0.3 * p_exp)
        if shift_y > 0:
            M_shift = np.float32([[1, 0, 0], [0, 1, shift_y]])
            crop = cv2.warpAffine(crop, M_shift, (w, h))
            
        # 4. Vertical Motion Blur (잔상 효과)
        # 세로 방향으로 강하게 블러를 줌
        blur_size = int(50 * p_exp)
        if blur_size >= 1:
            # 커널 생성: 세로로 긴 커널
            kernel_size = blur_size * 2 + 1
            kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
            
            # 세로 한 줄에 값을 채움 (Vertical Blur)
            center = int(kernel_size / 2)
            kernel[center-blur_size:center+blur_size+1, center] = 1.0 / (2 * blur_size + 1)
            
            # 필터 적용
            crop = cv2.filter2D(crop, -1, kernel)
            
        # 5. Zoom In (마지막 임팩트)
        zoom_scale = 1.0 + (0.5 * p_exp)
        if zoom_scale > 1.0:
            center_x, center_y = w // 2, h // 2
            M_zoom = cv2.getRotationMatrix2D((center_x, center_y), 0, zoom_scale)
            crop = cv2.warpAffine(crop, M_zoom, (w, h))
            
        return crop
