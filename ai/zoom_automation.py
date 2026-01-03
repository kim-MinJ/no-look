import pyautogui
import time
import pyperclip
import sys
from pynput import keyboard
import pygetwindow as gw

class ZoomAutomator:
    def __init__(self):
        # 안전장치: 마우스를 화면 모서리로 급히 옮기면 프로그램 중단
        pyautogui.FAILSAFE = True
        self.confirmed = False
        self.cancelled = False

    def _on_press(self, key):
        try:
            if key == keyboard.Key.enter:
                self.confirmed = True
                return False # 리스너 중단
            if key == keyboard.Key.shift_r:
                self.cancelled = True
                return False # 리스너 중단
        except AttributeError:
            pass

    def wait_for_user_confirmation(self, text):
        """
        사용자의 키 입력을 대기 (Enter: 전송, Right Shift: 취소)
        """
        print(f"\n📢 [AI 추천 답변]: {text}")
        print("👉 전송하려면 [Enter], 취소하려면 [오른쪽 Shift]를 누르세요...")
        
        self.confirmed = False
        self.cancelled = False
        
        with keyboard.Listener(on_press=self._on_press) as listener:
            listener.join()
        
        if self.confirmed:
            print("🚀 전송 중...")
            self.send_to_zoom(text)
            return True
        else:
            print("🛑 취소되었습니다.")
            return False

    def send_to_zoom(self, text):
        """
        줌 창을 찾아 활성화한 뒤, pyperclip/pyautogui를 사용하여 텍스트 전송
        """
        try:
            # 1. 줌 창 찾기 및 포커스 (자동 순간이동)
            print("🔍 줌 창 탐색 중...")
            zoom_windows = [w for w in gw.getAllWindows() if "Zoom" in w.title]
            
            if zoom_windows:
                # 가장 적절한 창 선택 (보통 첫 번째)
                zoom_win = zoom_windows[0]
                try:
                    if zoom_win.isMinimized:
                        zoom_win.restore()
                    zoom_win.activate()
                    print(f"✨ 줌 창 활성화 완료: {zoom_win.title}")
                    time.sleep(0.3) # 포커스 전환 대기
                except Exception as e:
                    print(f"⚠️ 창 활성화 실패 (수동 클릭 필요할 수 있음): {e}")
            else:
                print("⚠️ 줌 창을 찾지 못했습니다. 현재 활성화된 창에 전송을 시도합니다.")

            # 2. 한글 입력을 위해 클립보드 사용
            pyperclip.copy(text)
            
            # 2. 잠시 대기 (사용자가 Zoom 창으로 포커스를 옮길 시간을 줄 수도 있음)
            # 여기서는 이미 Zoom 채팅창에 커서가 있다고 가정하고 바로 붙여넣기 수행
            time.sleep(0.5)
            
            # 3. 붙여넣기 (Ctrl + V)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            
            # 4. 엔터 (전송)
            pyautogui.press('enter')
            print("✅ 전송 완료!")
            
        except Exception as e:
            print(f"❌ Zoom Automation Error: {e}")

if __name__ == "__main__":
    # 독립 테스트용
    automator = ZoomAutomator()
    sample_text = "안녕하세요, 테스트 답변입니다."
    automator.wait_for_user_confirmation(sample_text)
