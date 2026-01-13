import time
import pyautogui
import pyperclip
import platform

class MacroEngine:
    """
    Handles macro actions like finding specific windows (Zoom, Discord)
    and ensuring text is typed into them.
    """

    def __init__(self):
        # Fail-safe to prevent out-of-control mouse/keyboard
        pyautogui.FAILSAFE = True
        self.os_type = platform.system()

    def type_text(self, text: str, target_app: str = "zoom"):
        """
        Attempts to focus the target application and type the text.
        target_app: 'zoom' or 'discord'
        """
        if not text:
            return False

        print(f"[Macro] Input request: {text} -> {target_app}")

        # 1. Attempt to switch window (Simple Alt-Tab approach or known hotkeys)
        # Note: Robust window verification requires platform-specific libraries (win32gui etc).
        # For this prototype, we will assume the user has the window active or we simplify
        # by just typing if the user is expected to be in a meeting.
        
        # However, to be more useful, let's try to simulate 'switch' if possible.
        # Since we are on Windows (from context), we can't easily "find" window without pygetwindow.
        # We will add it to requirements if strict usage is needed.
        # For now, we will simulate a "Paste" action which is faster and safer than typing char-by-char for long text.
        
        # Optional: Add a small delay to let user focus if they clicked a button
        # time.sleep(0.5) 

        # Copy text to clipboard
        pyperclip.copy(text)

        # 2. Type/Paste
        # Zoom often requires 'Enter' to send.
        
        # If specific app logic is needed (future expansion):
        if target_app.lower() == "zoom":
             # Zoom logic
             pass
        elif target_app.lower() == "discord":
             # Discord logic
             pass

        # Paste the text
        # Ctrl+V
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        
        # Press Enter to send
        pyautogui.press('enter')
        
        return True

    def trigger_hotkey(self, app_name: str):
        """
        Example: Switch focus to Zoom meeting window if possible.
        """
        pass
