# ai/sound/stt_core.py
import os
import sys
import time
import re
import queue
from datetime import datetime

import speech_recognition as sr
from faster_whisper import WhisperModel

# ✅ ai/ 폴더(config_loader.py) import 가능하게 부모 경로 추가
BASE_AI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_AI_DIR not in sys.path:
    sys.path.append(BASE_AI_DIR)

from config_loader import load_config, get_transcript_path


def _safe_utf8_stdout():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


_safe_utf8_stdout()


class GhostEars:
    def __init__(self, config=None):
        if config is None:
            config = load_config()

        self.config = config
        self._apply_config(config)

        model_size = self.config.get("settings", {}).get("model_size", "medium")
        print(f"--- 🎧 [GhostEars] 모델 로딩 중... ({model_size}) ---")
        print(f"📌 트리거 키워드: {self.trigger_keywords}")

        self.model = None
        try:
            # ✅ GPU/cuDNN 없는 환경에서 오류 방지를 위해 CPU 명시 사용
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print("✅ 모델 로딩 완료!")
        except Exception as e:
            print(f"❌ 모델 로딩 실패: {e}")

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 100
        self.recognizer.dynamic_energy_threshold = True

        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.stopper = None

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_filename = os.path.join(base_dir, "temp_ghost_audio.wav")

        # ✅ transcript는 user 폴더로(쓰기 안전)
        self.transcript_file = str(get_transcript_path())

        self.full_history = []

        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- 🚀 [No-Look] 세션 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ({model_size}) ---\n")

    def _apply_config(self, config):
        settings = config.get("settings", {})
        triggers = config.get("triggers", {})

        self.device_index = settings.get("device_index", 0)
        self.language = settings.get("language", "ko")
        self.sample_rate = settings.get("sample_rate", 16000)

        self.trigger_keywords = triggers.get("keywords", [])
        self.question_patterns = triggers.get("question_patterns", ["?"])

    def reload_config(self):
        self.config = load_config()
        self._apply_config(self.config)
        print("🔄 설정 다시 로드됨!")
        print(f"📌 새 트리거 키워드: {self.trigger_keywords}")
        return True

    def _audio_callback(self, recognizer, audio):
        # 너무 많이 찍히면 콘솔 도배됨. 필요하면 주석 처리.
        # print(f"🎤 [Audio] signal (bytes={len(audio.get_raw_data())})")
        self.audio_queue.put(audio)

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

    def stop_listening(self):
        try:
            if self.stopper:
                self.stopper(wait_for_stop=False)
            self.is_listening = False
            return True
        except Exception as e:
            print(f"⚠️ [GhostEars] stop 실패: {e}")
            return False

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
                with open(self.temp_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())

                segments, info = self.model.transcribe(
                    self.temp_filename,
                    beam_size=5,
                    language=self.language,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )

                full_text = ""
                for segment in segments:
                    if segment.avg_logprob < -1.0:
                        # 환각/잡음 컷
                        continue
                    full_text += segment.text

                final_text = full_text.strip()
                if not final_text:
                    yield None
                    continue

                yield final_text

            except Exception as e:
                print(f"⚠️ [STT Core] 변환 중 에러: {e}")
                time.sleep(0.3)
                yield None

        if not drained:
            yield None

    def save_to_log(self, text):
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            entry = f"[{timestamp}] {text}"

            with open(self.transcript_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
                f.flush()

            self.full_history.append(entry)
        except Exception as e:
            print(f"❌ [Log Error] 저장 실패: {e}")

    def get_full_transcript(self):
        return "\n".join(self.full_history)

    def check_trigger(self, text):
        if not text:
            return None

        # 1) 질문 패턴
        for pattern in self.question_patterns:
            if pattern in text:
                return ("QUESTION", pattern)
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return ("QUESTION", pattern)
            except Exception:
                continue

        # 2) 키워드
        clean_text = re.sub(r"[^a-zA-Z0-9가-힣]", "", text)
        for keyword in self.trigger_keywords:
            clean_kw = re.sub(r"[^a-zA-Z0-9가-힣]", "", keyword)
            if not clean_kw:
                continue
            if clean_kw in clean_text:
                return ("KEYWORD", keyword)

        return None
