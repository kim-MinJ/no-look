import time
import threading
import os
import sys
from collections import deque
from typing import Optional

# ai/sound 폴더를 path에 추가하여 모듈 임포트 가능하게 함
current_dir = os.path.dirname(os.path.abspath(__file__))
sound_dir = os.path.join(current_dir, "sound")
if sound_dir not in sys.path:
    sys.path.append(sound_dir)

# Import dependencies
try:
    from macro_bot import MacroBot
    from zoom_automation import ZoomAutomator
    from stt_core import GhostEars, load_config
except ImportError as e:
    print(f"⚠️ [AutoAssistant] 모듈 임포트 경고: {e}")
    # 서버 실행 시점에는 에러가 안 나도록 처리 (실제 실행 시 에러 발생)


class AutoAssistantService:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.config = load_config()
        self.ears = None
        self.bot = None
        self.automator = None
        
        # State
        self.history = deque(maxlen=500)
        self.sentence_buffer = []
        self.last_received_time = 0.0
        self.MERGE_THRESHOLD = 2.0

        # Lazy init status
        self._initialized = False
        self._ai_busy = False
        self.last_suggestion = None
        self._lock = threading.Lock()
        self.last_heartbeat = time.time()  # ✅ [Add] STT 루프 생존 확인용
        self._watchdog_thread = None       # ✅ [Add] 감시 스레드

    def start(self):
        """서비스를 별도 스레드에서 시작"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # 워치독 스레드 시작
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
        
        print("🚀 [AutoAssistant] AI 비서 서비스 및 워치독 시작")

    def stop(self):
        """서비스 중지 요청"""
        if not self._running:
            return
            
        print("🛑 [AutoAssistant] 서비스 종료 중...")
        self._running = False
        
        # GhostEars의 리스닝 중단
        if self.ears and hasattr(self.ears, 'stopper'):
            try:
                self.ears.stopper(wait_for_stop=False)
            except Exception as e:
                print(f"⚠️ [AutoAssistant] Stopper error: {e}")

        # 스레드 종료 대기 (FastAPI 응답 지연 방지를 위해 짧게 설정)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            self._thread = None
        
        print("👋 [AutoAssistant] 서비스 중지 신호 전달 완료")

    def _initialize_models(self):
        """무거운 모델 로딩"""
        if self._initialized:
            return True
            
        try:
            print("⏳ [AutoAssistant] 모델 초기화 중... (시간이 걸릴 수 있습니다)")
            self.ears = GhostEars(self.config)
            self.bot = MacroBot()
            self.automator = ZoomAutomator()
            self._initialized = True
            print("✅ [AutoAssistant] 모델 로딩 완료!")
            return True
        except Exception as e:
            print(f"❌ [AutoAssistant] 모델 로딩 실패: {e}")
            return False

    def _run_loop(self):
        """실제 작업이 돌아가는 메인 루프 (Thread Safe)"""
        if not self._initialize_models():
            self._running = False
            return

        print(f"🎤 마이크 인덱스: {self.ears.device_index}")
        
        if not self.ears.start_listening():
            print("❌ [AutoAssistant] 마이크 리스닝 시작 실패")
            self._running = False
            return

        print("👂 [AutoAssistant] 듣기 시작... (서버 백그라운드)")
        
        self.last_received_time = time.time()
        self.sentence_buffer = []

        try:
            while self._running:
                # GhostEars.process_queue() generator 사용
                for text in self.ears.process_queue():
                    if not self._running: 
                        break
                        
                    # 💓 하트비트 갱신 (None인 경우에도 엔진은 살아있음)
                    self.last_heartbeat = time.time()
                    
                    if text:
                        self._handle_text(text)
                
                if not self._running:
                    break
                time.sleep(0.1)

        except Exception as e:
            print(f"⚠️ [AutoAssistant] 런타임 에러: {e}")
        finally:
            print("💤 [AutoAssistant] 루프 종료")

    def _watchdog_loop(self):
        """STT 루프가 죽었는지 감시하고 필요시 재시작 (Self-healing)"""
        print("🕵️ [AutoAssistant] 워치독 감시 시작")
        while self._running:
            time.sleep(5) # 5초마다 체크
            
            idle_time = time.time() - self.last_heartbeat
            if idle_time > 15: # 15초 이상 하트비트가 없으면 문제 발생으로 판단
                print(f"🚨 [Watchdog] STT 엔진 멈춤 감지 ({idle_time:.1s}s 무응답). 재시작 시도...")
                
                # 강제 재시작 로직
                try:
                    if self.ears:
                        self.ears.stopper(wait_for_stop=False)
                    time.sleep(1)
                    if self.ears.start_listening():
                        self.last_heartbeat = time.time()
                        print("✨ [Watchdog] STT 엔진 재시작 성공!")
                    else:
                        print("❌ [Watchdog] STT 엔진 재시작 실패")
                except Exception as e:
                    print(f"❌ [Watchdog] 복구 시도 중 에러: {e}")

    def _handle_text(self, text: str):
        """텍스트 처리 및 답변 생성 로직 (Thread Safe)"""
        current_time = time.time()
        
        # 로그 저장은 락 밖에서 수행 (I/O 병목 방지)
        self.ears.save_to_log(text)
        print(f"▶ [STT]: {text}")

        with self._lock:
            # 1. 문장 병합 로직
            if current_time - self.last_received_time < self.MERGE_THRESHOLD:
                self.sentence_buffer.append(text)
            else:
                if self.sentence_buffer:
                    merged_sentence = " ".join(self.sentence_buffer)
                    self.history.append(merged_sentence)
                self.sentence_buffer = [text]
            
            self.last_received_time = current_time
            current_processing_text = " ".join(self.sentence_buffer)

        # 2. 트리거 체크 (락 밖에서 수행 가능)
        trigger = self.ears.check_trigger(current_processing_text)
        if trigger:
            if self._ai_busy:
                return

            with self._lock:
                context_snapshot = list(self.history)
                self.sentence_buffer = []
            
            threading.Thread(
                target=self._handle_trigger, 
                args=(trigger, current_processing_text, context_snapshot),
                daemon=True
            ).start()

    def _handle_trigger(self, trigger, current_processing_text, context_snapshot):
        self._ai_busy = True  # ✅ [Add] AI 시작
        self.last_suggestion = None # ✅ [Add] 새로운 고민 시작 시 이전 추천 초기화
        try:
            trigger_type, matched = trigger
            print(f"🎯 [AutoAssistant] 트리거 감지! ({trigger_type}: {matched})")
            
            # ✅ [Fix] 답변 생성이 오래 걸릴 수 있으므로, 텍스트를 즉시 히스토리에 반영하여 사용자가 대기하지 않게 함
            with self._lock:
                self.history.append(current_processing_text)
                
            print("⏳ [AutoAssistant] 답변 생성 중... (STT는 계속 동작합니다)")
            
            # 답변 생성
            try:
                print("🤖 [AutoAssistant] AI 답변 제안 생성 시작...")
                suggestion = self.bot.get_suggestion(current_processing_text, context_snapshot)
                
                if suggestion:
                    print("-" * 50)
                    print(f"💡 [AI 추천 답변]: {suggestion}")
                    print("-" * 50)
                    self.last_suggestion = suggestion # ✅ [Add] 생성된 답변 저장
                else:
                    print("⚠️ [AutoAssistant] 답변 생성 실패")
            except Exception as e:
                print(f"❌ [AutoAssistant] 답변 생성 중 에러 발생: {e}")
        finally:
            # ✅ [Add] 쿨다운: 생성 후 3초간은 새로운 답변을 생성하지 않음 (안정성)
            time.sleep(3.0)
            self._ai_busy = False
            print("✅ [AutoAssistant] AI 고민 완료 (다음 대기 중)")

    def get_transcript_state(self):
        """현재 STT 상태 반환 (history + current buffer + suggestion)"""
        with self._lock:
            return {
                "history": list(self.history),
                "current": " ".join(self.sentence_buffer) if self.sentence_buffer else "",
                "suggestion": self.last_suggestion # ✅ [Add] 프론트엔드로 전달
            }

# Singleton instance
assistant_service = AutoAssistantService()

if __name__ == "__main__":
    # Test execution
    svc = AutoAssistantService()
    svc.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        svc.stop()