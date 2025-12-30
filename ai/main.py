import cv2
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from detector import DistractionDetector
from generator import StreamGenerator
from bridge import VirtualCam
from bot import MeetingBot


def main():
    WEBCAM_ID = 0

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    FAKE_VIDEO = os.path.join(BASE_DIR, "assets", "fake_sample.mp4")

    detector = DistractionDetector()
    generator = StreamGenerator(FAKE_VIDEO)
    bot = MeetingBot()

    cap = cv2.VideoCapture(WEBCAM_ID)
    if not cap.isOpened():
        raise RuntimeError(f"Webcam open failed: {WEBCAM_ID}")

    bridge = VirtualCam(
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )

    # ✅ 미리 창 만들기 (버튼/트랙바 부착 대상)
    WIN = "No-Look Preview"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)

    mode = "REAL"
    trans_start = time.time()
    TRANSITION_TIME = 0.5

    locked_fake = False          # 딴짓 한번이면 FAKE 고정
    pause_fake_playback = False  # ✅ 버튼으로 FAKE 영상 재생 일시정지
    force_real = False           # ✅ 버튼으로 REAL 강제 복귀

    last_fake_frame = None       # pause 중에 계속 보여줄 마지막 프레임
    reaction_text = ""
    reaction_sent = False

    # ----------------------------
    # UI 컨트롤: 버튼(가능하면) / 아니면 트랙바로 대체
    # ----------------------------
    def set_pause(v):
        nonlocal pause_fake_playback
        pause_fake_playback = bool(v)

    def set_force_real(v):
        nonlocal force_real
        force_real = bool(v)

    ui_mode = "none"

    # 1) Qt 버튼 시도
    try:
        # OpenCV가 Qt로 빌드된 경우에만 동작
        cv2.createButton(
            "Pause Fake (toggle)",
            lambda *_: set_pause(0 if pause_fake_playback else 1),
            None,
            cv2.QT_PUSH_BUTTON,
            0
        )
        cv2.createButton(
            "Force REAL (toggle)",
            lambda *_: set_force_real(0 if force_real else 1),
            None,
            cv2.QT_PUSH_BUTTON,
            0
        )
        ui_mode = "button"
    except Exception:
        # 2) 어디서든 동작하는 트랙바(0/1 스위치)로 대체
        cv2.createTrackbar("PauseFake 0/1", WIN, 0, 1, lambda v: set_pause(v))
        cv2.createTrackbar("ForceREAL 0/1", WIN, 0, 1, lambda v: set_force_real(v))
        ui_mode = "trackbar"

    # ----------------------------
    # Main loop
    # ----------------------------
    while True:
        ret, real_frame = cap.read()
        if not ret:
            break

        # 1) Detect
        is_distracted, reasons = detector.is_distracted(real_frame)

        # 2) 락 걸기 (단, Force REAL이면 락을 무시)
        if not force_real and is_distracted and not locked_fake:
            locked_fake = True
            if not reaction_sent:
                reaction_text = bot.get_reaction()
                reaction_sent = True

        # 3) 목표 모드 결정
        if force_real:
            target_mode = "REAL"
        else:
            target_mode = "FAKE" if locked_fake else "REAL"

        # 4) 모드 전환 타이밍 갱신
        if target_mode != mode:
            mode = target_mode
            trans_start = time.time()

        # 5) 블렌딩 비율
        elapsed = time.time() - trans_start
        progress = min(elapsed / TRANSITION_TIME, 1.0)
        final_ratio = progress if mode == "FAKE" else (1.0 - progress)

        # 6) fake_frame 가져오기 (✅ pause면 재생 멈추고 last_fake_frame 고정)
        if mode == "FAKE":
            if pause_fake_playback and last_fake_frame is not None:
                fake_frame = last_fake_frame
            else:
                fake_frame = generator.get_fake_frame()
                if fake_frame is None:
                    fake_frame = real_frame.copy()
                else:
                    last_fake_frame = fake_frame
        else:
            fake_frame = None  # REAL일 때는 사용 안 함

        # 7) 크기 맞추기 + 블렌드
        if fake_frame is None:
            output_frame = real_frame
        else:
            fake_frame = cv2.resize(fake_frame, (real_frame.shape[1], real_frame.shape[0]))
            output_frame = generator.blend_frames(real_frame, fake_frame, final_ratio)

        # 8) Output
        bridge.send(output_frame)

        # Debug overlay
        debug_img = output_frame.copy()
        color = (0, 0, 255) if (mode == "FAKE") else (0, 255, 0)

        status_text = f"Mode:{mode} {int(final_ratio*100)}% | Locked:{locked_fake} | PauseFake:{pause_fake_playback} | ForceREAL:{force_real} | UI:{ui_mode}"
        cv2.putText(debug_img, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        if reasons:
            cv2.putText(debug_img, str(reasons), (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1)

        if reaction_text:
            cv2.putText(debug_img, reaction_text, (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow(WIN, debug_img)

        # 키보드 백업(버튼 안 될 때도 조작 가능)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('p'):  # pause toggle
            pause_fake_playback = not pause_fake_playback
        elif k == ord('r'):  # force real toggle
            force_real = not force_real

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()