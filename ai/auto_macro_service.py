# ai/auto_macro_service.py
import time
import threading
import os
import sys
from collections import deque
from typing import Optional

# ai/sound 폴더 import 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sound_dir = os.path.join(current_dir, "sound")
if sound_dir not in sys.path:
    sys.path.append(sound_dir)

from macro_bot import MacroBot
from zoom_automation import ZoomAutomator
from stt_core import GhostEars
from config_loader import load_config


class AutoAssistantService:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.config = load_config()

        self.ears: Optional[GhostEars] = None
        self.bot: Optional[MacroBot] = None
        self.automator: Optional[ZoomAutomator] = None

        self.history = deque(maxlen=500)
        self.sentence_buffer = []
        self.last_received_time = 0.0
        self.MERGE_THRESHOLD = 2.0

        self._initialized = False
        self._ai_busy = False
        self.last_suggestion = None
        self._lock = threading.Lock()

        # ✅ 워치독은 "리스닝 시작 이후"에만 의미 있음
        self.last_heartbeat = time.time()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_enabled = False  # ✅ 리스닝 성공 후 True

    def start(self):
        if self._running and self._thread and self._thread.is_alive():
            print("⚠️ [AutoAssistant] 이미 실행 중")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        print("🚀 [AutoAssistant] 서비스 시작")

    def stop(self):
        if not self._running:
            return

        print("🛑 [AutoAssistant] 종료 중...")
        self._running = False
        self._watchdog_enabled = False

        if self.ears:
            self.ears.stop_listening()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            self._thread = None

        print("👋 [AutoAssistant] 종료 완료")

    def _initialize_models(self):
        if self._initialized:
            return True

        try:
            print("⏳ [AutoAssistant] 초기화 중...")
            self.config = load_config()

            # ✅ 여기서 모델 로딩이 오래 걸려도 워치독은 안 돎
            self.ears = GhostEars(self.config)
            self.bot = MacroBot()
            self.automator = ZoomAutomator()

            self._initialized = True
            print("✅ [AutoAssistant] 초기화 완료")
            return True
        except Exception as e:
            print(f"❌ [AutoAssistant] 초기화 실패: {e}")
            return False

    def _start_watchdog_if_needed(self):
        """✅ 리스닝 성공 이후에만 워치독 시작"""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_enabled = True
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def _run_loop(self):
        if not self._initialize_models():
            self._running = False
            return

        print(f"🎤 마이크 인덱스: {self.ears.device_index}")

        # ✅ 리스닝 성공해야 워치독 시작
        if not self.ears.start_listening():
            print("❌ [AutoAssistant] 마이크 리스닝 시작 실패")
            self._running = False
            return

        # ✅ 여기서부터 워치독 ON
        self.last_heartbeat = time.time()
        self._start_watchdog_if_needed()

        print("👂 [AutoAssistant] 듣기 시작")

        self.last_received_time = time.time()
        self.sentence_buffer = []

        try:
            while self._running:
                # ✅ 루프 생존 하트비트
                self.last_heartbeat = time.time()

                for text in self.ears.process_queue():
                    if not self._running:
                        break

                    self.last_heartbeat = time.time()

                    if text:
                        self._handle_text(text)

                time.sleep(0.05)

        except Exception as e:
            print(f"⚠️ [AutoAssistant] 런타임 에러: {e}")
        finally:
            print("💤 [AutoAssistant] 루프 종료")

    def _watchdog_loop(self):
        print("🕵️ [AutoAssistant] 워치독 시작")
        while self._running:
            time.sleep(5)

            # ✅ 리스닝 성공 전이면 감시하지 않음
            if not self._watchdog_enabled:
                continue

            idle = time.time() - self.last_heartbeat
            if idle > 20:
                print(f"🚨 [Watchdog] 무응답 {idle:.1f}s → 리스너 재시작 시도")
                try:
                    if self.ears:
                        self.ears.stop_listening()
                        time.sleep(1)
                        if self.ears.start_listening():
                            self.last_heartbeat = time.time()
                            print("✨ [Watchdog] 재시작 성공")
                        else:
                            print("❌ [Watchdog] 재시작 실패")
                except Exception as e:
                    print(f"❌ [Watchdog] 복구 실패: {e}")

    def _handle_text(self, text: str):
        now = time.time()
        self.ears.save_to_log(text)
        print(f"▶ [STT]: {text}")

        with self._lock:
            if now - self.last_received_time < self.MERGE_THRESHOLD:
                self.sentence_buffer.append(text)
            else:
                if self.sentence_buffer:
                    merged = " ".join(self.sentence_buffer)
                    self.history.append({"text": merged, "timestamp": self.last_received_time})
                self.sentence_buffer = [text]

            self.last_received_time = now
            current_processing_text = " ".join(self.sentence_buffer)

        trigger = self.ears.check_trigger(current_processing_text)
        if trigger:
            if self._ai_busy:
                return

            with self._lock:
                context_snapshot = [item["text"] for item in self.history]
                self.sentence_buffer = []

            threading.Thread(
                target=self._handle_trigger,
                args=(trigger, current_processing_text, context_snapshot),
                daemon=True
            ).start()

    def _handle_trigger(self, trigger, current_processing_text, context_snapshot):
        self._ai_busy = True
        self.last_suggestion = None
        try:
            trigger_type, matched = trigger
            print(f"🎯 [AutoAssistant] 트리거 감지 ({trigger_type}: {matched})")

            with self._lock:
                self.history.append({"text": current_processing_text, "timestamp": time.time()})

            print("⏳ [AutoAssistant] 답변 생성 중...")
            suggestion = self.bot.get_suggestion(current_processing_text, context_snapshot)

            if suggestion:
                print("-" * 50)
                print(f"💡 [AI 추천 답변]: {suggestion}")
                print("-" * 50)
                self.last_suggestion = suggestion
            else:
                print("⚠️ [AutoAssistant] 답변 생성 실패")

        except Exception as e:
            print(f"❌ [AutoAssistant] 답변 생성 에러: {e}")
        finally:
            time.sleep(3.0)
            self._ai_busy = False
            print("✅ [AutoAssistant] 대기")

    def get_transcript_state(self):
        with self._lock:
            return {
                "history": list(self.history),
                "current": " ".join(self.sentence_buffer) if self.sentence_buffer else "",
                "suggestion": self.last_suggestion,
            }


assistant_service = AutoAssistantService()
