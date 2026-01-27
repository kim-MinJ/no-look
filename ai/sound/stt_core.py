# ai/sound/stt_core.py
import os
import sys
import time
import re
import queue
from datetime import datetime

import speech_recognition as sr
from faster_whisper import WhisperModel

# ai/ 폴더(config_loader.py) import 가능하게 부모 경로 추가
BASE_AI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_AI_DIR not in sys.path:
    sys.path.append(BASE_AI_DIR)

from config_loader import load_config, get_transcript_path

# 한글 인코딩 유틸리티
def _safe_utf8_stdout():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


_safe_utf8_stdout()

# 핵심 기능
class GhostEars:
    def __init__(self, config=None):
        # 모델, 마이크, 큐 준비
        if config is None:
            config = load_config()

        self.config = config
        self._apply_config(config)

        # Config 로드 (모델)
        model_size = self.config.get("settings", {}).get("model_size", "medium")
        print(f"--- 🎧 [GhostEars] 모델 로딩 중... ({model_size}) ---")
        print(f"📌 트리거 키워드: {self.trigger_keywords}")

        # WhisperModel 로딩: GPU(cuda) 우선 → 실패 시 CPU(int8) fallback
        self.model = None
        try:
            # RTX 4050이면 여기로 붙는 게 정상 (CUDA가 제대로 설치/연동돼 있다면)
            self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
            print("✅ 모델 로딩 완료! (GPU: cuda, float16)")
        except Exception as e:
            # CPU 로딩 (GPU 실패시)
            print(f"⚠️ GPU 로딩 실패 → CPU로 fallback: {e}")
            try:
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
                print("✅ 모델 로딩 완료! (CPU: int8)")
            except Exception as e2:
                print(f"❌ 모델 로딩 실패: {e2}")
                self.model = None

        # 마이크 인식기 준비
        self.recognizer = sr.Recognizer() # 소리 감지
        self.recognizer.energy_threshold = 100 # 마이크 감도
        self.recognizer.dynamic_energy_threshold = True # 주변 소음에 맞춰 감도 자동 조절

        # 오디오 큐
        # 마이크(Producer)가 듣는 즉시 여기에 데이터를 '밀어 넣고(Put)'
        # 나중에 STT(Consumer)가 여기서 '꺼내서(Get)' 처리
        # 이렇게 안 하면 STT 처리하는 동안 마이크가 먹통이 됨 (Non-blocking)
        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.stopper = None

        # 임시 오디오 파일
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_filename = os.path.join(base_dir, "temp_ghost_audio.wav")

        # transcript는 user 폴더로(쓰기 안전)
        self.transcript_file = str(get_transcript_path())
        self.full_history = []

        with open(self.transcript_file, "a", encoding="utf-8-sig") as f:
            f.write(
                f"\n\n--- 🚀 [No-Look] 세션 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ({model_size}) ---\n"
            )

    # Config 적용
    def _apply_config(self, config):
        settings = config.get("settings", {})
        triggers = config.get("triggers", {})

        self.device_index = settings.get("device_index", 5)
        self.language = settings.get("language", "ko")
        self.sample_rate = settings.get("sample_rate", 16000)

        self.trigger_keywords = triggers.get("keywords", [])
        self.question_patterns = triggers.get("question_patterns", ["?"])

    # Config 재로드
    def reload_config(self):
        self.config = load_config()
        self._apply_config(self.config)
        print("🔄 설정 다시 로드됨!")
        print(f"📌 새 트리거 키워드: {self.trigger_keywords}")
        return True
    
    # 오디오 큐에 오디오 데이터 추가
    def _audio_callback(self, recognizer, audio):
        self.audio_queue.put(audio)

    # 마이크 리스닝 시작
    def start_listening(self):
        if self.is_listening:
            print("⚠️ [GhostEars] 이미 리스닝 중")
            return True

        try:
            self.source = sr.Microphone(device_index=self.device_index, sample_rate=self.sample_rate)
            print(f"👂 [GhostEars] Listening... (Rate: {self.sample_rate}Hz, device_index={self.device_index})")

            self.stopper = self.recognizer.listen_in_background(
                self.source,
                self._audio_callback,
                phrase_time_limit=5,
            )
            self.is_listening = True
            return True
        except Exception as e:
            print(f"❌ [GhostEars] 마이크 초기화 실패: {e}")
            return False

    # 마이크 리스닝 중지
    def stop_listening(self):
        try:
            if self.stopper:
                self.stopper(wait_for_stop=False)
            self.is_listening = False
            return True
        except Exception as e:
            print(f"⚠️ [GhostEars] stop 실패: {e}")
            return False

    # 오디오 큐 처리
    def process_queue(self):
        """
        ✅ 무한 while로 timeout 0.01 돌리는 방식(고CPU) 대신,
        현재 큐에 쌓인 오디오를 "있는 만큼만" 처리하고 끝냄.
        """
        if self.model is None:
            yield None
            return

        drained = False

        while True:
            try:
                audio_data = self.audio_queue.get_nowait()
            except queue.Empty:
                break

            drained = True

            try:
                # 성능 측정 시작
                start_time = time.time()
                print("⏳ 오디오 인식중...", end="\r") # 줄바꿈 없이 덮어쓰기 효과

                with open(self.temp_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())

                segments, info = self.model.transcribe(
                    self.temp_filename,
                    beam_size=5,
                    language=self.language,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )
                
                # 성능 측정 종료
                processing_time = time.time() - start_time
                audio_duration = info.duration
                rtf = processing_time / audio_duration if audio_duration > 0 else 0

                full_text = ""
                for segment in segments:
                    if segment.avg_logprob < -1.0:
                        # 환각/잡음 컷
                        continue
                    full_text += segment.text
                
                final_text = full_text.strip()
                
                # [필터링] Whisper 고질병 (환각) 제거
                hallucinations = [
                    "시청해주셔서", "MBC 뉴스", "구독과 좋아요", 
                    "자막 제작", "제작:", "특수효과", "포커스였습니다"
                ]
                is_hallucination = any(h in final_text for h in hallucinations) if final_text else False

                if not final_text or is_hallucination:
                    yield None
                    continue

                # 로그 출력
                print(f"⚡ 오디오: {audio_duration:.2f}초 | 처리: {processing_time:.2f}초 | RTF: {rtf:.4f}")

                yield final_text

            except Exception as e:
                print(f"⚠️ [STT Core] 변환 중 에러: {e}")
                time.sleep(0.3)
                yield None

        if not drained:
            yield None

    # 로그 저장
    def save_to_log(self, text):
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            entry = f"[{timestamp}] {text}"

            with open(self.transcript_file, "a", encoding="utf-8-sig") as f:
                f.write(entry + "\n")
                f.flush()

            self.full_history.append(entry)
            print(f"💾 [Log] 저장됨: {self.transcript_file}")  # <--- 확인용 출력
        except Exception as e:
            print(f"❌ [Log Error] 저장 실패: {e}")

    # 전체 로그 가져오기
    def get_full_transcript(self):
        return "\n".join(self.full_history)
    
    # 트리거 확인
    def check_trigger(self, text):
        """
        - 키워드가 있을 때만 트리거 발동
        - 키워드 없으면: 무조건 None
        - 키워드 있으면: (question_patterns 있으면 QUESTION 우선) 없으면 KEYWORD
        """
        if not text:
            return None

        raw_text = text.strip()

        #  키워드 먼저 탐지 (게이트)
        clean_text = re.sub(r"[^a-zA-Z0-9가-힣]", "", raw_text)

        matched_keyword = None
        for keyword in self.trigger_keywords:
            clean_kw = re.sub(r"[^a-zA-Z0-9가-힣]", "", str(keyword))
            if not clean_kw:
                continue
            if clean_kw in clean_text:
                matched_keyword = keyword
                break

        #  키워드 없으면 절대 트리거 안 함
        if not matched_keyword:
            return None

        #  키워드가 있을 때만 질문 패턴 체크
        for pattern in self.question_patterns:
            if not pattern:
                continue
            if str(pattern) in raw_text:
                return ("QUESTION", pattern)
            try:
                if re.search(str(pattern), raw_text, re.IGNORECASE):
                    return ("QUESTION", pattern)
            except Exception:
                continue

        #  질문 패턴 없으면 키워드 트리거
        return ("KEYWORD", matched_keyword)

if __name__ == "__main__":
    print("🎤 [Test Mode] STT Core 직접 실행 중...")
    
    try:
        # 설정 임의 로드 (없으면 기본값)
        stt = GhostEars()
        
        if stt.start_listening():
            print("💬 메인 루프 시작 (Ctrl+C로 종료)")
            while True:
                # 큐 처리 (generator)
                for text in stt.process_queue():
                    if text:
                        print(f"📝 인식됨: {text}")
                        stt.save_to_log(text)  # <--- 로그 저장 추가
                        
                        # 트리거 체크 테스트
                        trigger = stt.check_trigger(text)
                        if trigger:
                            print(f"🔔 트리거 감지: {trigger}")
                            
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 종료 요청됨")
    except Exception as e:
        print(f"\n❌ 실행 중 에러 발생: {e}")
    finally:
        if 'stt' in locals() and stt:
            stt.stop_listening()
        print("👋 종료 완료")
