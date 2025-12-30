import speech_recognition as sr
from faster_whisper import WhisperModel
import os
import json
import sys

# Windows 콘솔 인코딩 설정 (이모지 출력용)
sys.stdout.reconfigure(encoding='utf-8')

# === Config 로딩 ===
def load_config():
    """config.json 파일을 읽어서 설정 반환"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️ config.json 없음. 기본값 사용")
        return {
            "triggers": {"keywords": [], "question_patterns": ["?"]},
            "settings": {"device_index": 0, "model_size": "small", "language": "ko"}
        }


class GhostEars:
    def __init__(self, config=None):
        """
        config: config.json에서 로드한 설정 딕셔너리
        """
        if config is None:
            config = load_config()
        
        self.config = config
        self._apply_config(config)
        
        model_size = self.config.get("settings", {}).get("model_size", "small")
        print(f"--- 🎧 [GhostEars] 모델 로딩 중... ({model_size}) ---")
        print(f"📌 트리거 키워드: {self.trigger_keywords}")
        
        try:
            self.model = WhisperModel(model_size, device="cuda", compute_type="int8")
            print("✅ 모델 로딩 완료!")
        except Exception as e:
            print(f"❌ 모델 로딩 실패: {e}")
            self.model = None
            
        self.recognizer = sr.Recognizer()
        self.temp_filename = "temp_ghost_audio.wav"

    def _apply_config(self, config):
        """설정값을 인스턴스 변수에 적용"""
        settings = config.get("settings", {})
        triggers = config.get("triggers", {})
        
        # 설정값 추출
        self.device_index = settings.get("device_index", 0)
        self.language = settings.get("language", "ko")
        
        # 트리거 설정
        self.trigger_keywords = triggers.get("keywords", [])
        self.question_patterns = triggers.get("question_patterns", ["?"])

    def reload_config(self):
        """
        config.json을 다시 읽어서 트리거 설정 갱신
        Frontend에서 설정 변경 후 호출
        """
        self.config = load_config()
        self._apply_config(self.config)
        print(f"🔄 설정 다시 로드됨!")
        print(f"📌 새 트리거 키워드: {self.trigger_keywords}")
        return True

    def check_trigger(self, text):
        """
        텍스트에서 트리거 감지
        Returns: 
            - "KEYWORD": 키워드 감지됨
            - "QUESTION": 질문 패턴 감지됨
            - None: 트리거 없음
        """
        if not text:
            return None
            
        # 1. 키워드 체크 (이름 등)
        for keyword in self.trigger_keywords:
            if keyword in text:
                return ("KEYWORD", keyword)
        
        # 2. 질문 패턴 체크
        for pattern in self.question_patterns:
            if pattern in text:
                return ("QUESTION", pattern)
        
        return None

    def listen_and_transcribe(self):
        """마이크에서 오디오를 듣고 텍스트로 변환"""
        try:
            with sr.Microphone(device_index=self.device_index, sample_rate=44100) as source:
                print("👂 [Listening] 듣는 중...")
                audio_data = self.recognizer.listen(source, timeout=3, phrase_time_limit=5)
                
                with open(self.temp_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())
                
                segments, info = self.model.transcribe(
                    self.temp_filename, 
                    beam_size=5, 
                    language=self.language,
                    initial_prompt="회의, 수업, 발표, 질문, 학생, 교수",  # 컨텍스트 힌트
                    vad_filter=True,  # 음성 구간만 인식 (노이즈 제거)
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                
                full_text = ""
                for segment in segments:
                    full_text += segment.text
                
                return full_text.strip()

        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            return None


# === 테스트 실행 ===
if __name__ == "__main__":
    # Config 로드 및 시작
    config = load_config()
    ears = GhostEars(config)
    
    print("\n🚀 [STT 시스템 가동]")
    print(f"🎯 감지할 키워드: {ears.trigger_keywords}")
    print("-" * 40)
    
    while True:
        text = ears.listen_and_transcribe()
        
        if text:
            print(f"▶ 인식됨: {text}")
            
            # 트리거 체크
            trigger = ears.check_trigger(text)
            
            if trigger:
                trigger_type, matched = trigger
                if trigger_type == "KEYWORD":
                    print(f"🚨 [긴급] 키워드 '{matched}' 감지! → 자동 응답 필요!")
                elif trigger_type == "QUESTION":
                    print(f"❓ [질문 감지] 질문 패턴 '{matched}' 감지됨")