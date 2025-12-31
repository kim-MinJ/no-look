import cv2


class StreamGenerator:
    def __init__(self, video_path):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            print(f"Warning: Failed to load fake video at {video_path}")

    def reload(self, video_path: str):
        """✅ 런타임에 fake 소스 영상 교체"""
        self.video_path = video_path
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass

        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            print(f"Warning: Failed to load fake video at {video_path}")

    def get_fake_frame(self):
        """Returns the next frame from the loop."""
        if not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()

        return frame

    def blend_frames(self, real, fake, ratio):
        """
        Blend real and fake frames.
        Ratio 0.0 -> 100% Real
        Ratio 1.0 -> 100% Fake
        """
        if real is None or fake is None:
            return real if real is not None else fake

        if real.shape != fake.shape:
            fake = cv2.resize(fake, (real.shape[1], real.shape[0]))

        # alpha * src1 + beta * src2 + gamma
        return cv2.addWeighted(real, 1.0 - ratio, fake, ratio, 0.0)
