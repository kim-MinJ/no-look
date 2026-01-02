import speech_recognition as sr
from faster_whisper import WhisperModel
import os
import json
import sys
import queue
import time
import re

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
            "settings": {"device_index": 0, "model_size": "medium", "language": "ko", "sample_rate": 48000}
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
        
        model_size = self.config.get("settings", {}).get("model_size")
        print(f"--- 🎧 [GhostEars] 모델 로딩 중... ({model_size}) ---")
        print(f"📌 트리거 키워드: {self.trigger_keywords}")
        
        try:
            self.model = WhisperModel(model_size, device="auto", compute_type="int8")
            print("✅ 모델 로딩 완료!")
        except Exception as e:
            print(f"❌ 모델 로딩 실패: {e}")
            self.model = None
            
        self.recognizer = sr.Recognizer()
        # 가상 케이블 소리는 작을 수 있으므로 문턱값을 낮춤
        self.recognizer.energy_threshold = 100 
        self.recognizer.dynamic_energy_threshold = True
        
        
        # [Queue] 오디오 데이터 대기열 (비동기 처리용)
        self.audio_queue = queue.Queue()
        
        # 현재 파일 위치(ai/sound) 기준으로 경로 설정 (어디서 실행하든 여기 저장됨)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_filename = os.path.join(base_dir, "temp_ghost_audio.wav")
        self.transcript_file = os.path.join(base_dir, "transcript.txt")
        
        # [Memory] 전체 대화 히스토리 (요약/매크로용)
        self.full_history = []
        
        # [로그] 대화 내용 저장용 파일 (기존 기록 유지하며 시작 구분선만 추가)
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- 🚀 [No-Look] 세션 시작: {time.strftime('%Y-%m-%d %H:%M:%S')} ({model_size}) ---\n")

    def _audio_callback(self, recognizer, audio):
        """백그라운드에서 오디오가 캡처되면 Queue에 넣음"""
        print(f"🎤 [Audio] 신호 감지됨! (데이터 크기: {len(audio.get_raw_data())} bytes)")
        self.audio_queue.put(audio)

    def start_listening(self):
        """백그라운드 리스닝 시작"""
        try:
            self.source = sr.Microphone(device_index=self.device_index, sample_rate=self.sample_rate)
            print(f"👂 [Background Listening] 백그라운드 청취 시작... (Rate: {self.sample_rate}Hz)")
            
            # listen_in_background는 별도 스레드에서 동작함
            self.stopper = self.recognizer.listen_in_background(
                self.source, 
                self._audio_callback, 
                phrase_time_limit=5 # 응답 속도를 위해 짧게 끊음
            )
            return True
        except Exception as e:
            print(f"❌ 마이크 초기화 실패: {e}")
            return False

    def process_queue(self):
        """Queue에 쌓인 오디오를 하나씩 꺼내서 처리 (제너레이터)"""
        while True:
            try:
                # 0.5초마다 큐 확인
                audio_data = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                yield None
                continue
            
            # 오디오 처리 (기존 로직)
            try:
                print("⚡ [Processing] 오디오 변환 중...")
                with open(self.temp_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())
                
                segments, info = self.model.transcribe(
                    self.temp_filename, 
                    beam_size=5, 
                    language=self.language,
                    vad_filter=True, 
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                
                full_text = ""
                for segment in segments:
                    if segment.avg_logprob < -1.0:
                        print(f"👻 [Ghost Filter] 환각 제거됨 ({segment.avg_logprob:.2f}): {segment.text}")
                        continue
                    full_text += segment.text
                
                
                final_text = full_text.strip()
                if not final_text:
                    print("💨 [Skipped] 인식된 내용 없음 (잡음 또는 침묵)")
                    yield None
                    continue
                    
                yield final_text
                
            except Exception as e:
                print(f"⚠️ 변환 중 에러: {e}")
                yield None

    def save_to_log(self, text):
        """인식된 텍스트를 파일 및 메모리에 저장 (GPT가 읽어갈 용도)"""
        timestamp = time.strftime("[%H:%M:%S]")
        entry = f"{timestamp} {text}"
        
        # 파일 저장
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"{entry}\n")
            
        # 메모리 저장
        self.full_history.append(entry)

    def get_full_transcript(self):
        """지금까지의 전체 대화 내용을 하나로 합쳐서 반환"""
        return "\n".join(self.full_history)

    def _apply_config(self, config):
        """설정값을 인스턴스 변수에 적용"""
        settings = config.get("settings", {})
        triggers = config.get("triggers", {})
        
        # 설정값 추출
        self.device_index = settings.get("device_index", 0)
        self.language = settings.get("language", "ko")
        self.sample_rate = settings.get("sample_rate", 16000)
        
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
        텍스트에서 트리거 감지 (정규식 기반 지능형 감지)
        """
        if not text:
            return None
            
        # 검색 품질을 위해 공백 및 특수문자 제거 버전 준비
        clean_text = re.sub(r'[^a-zA-Z0-9가-힣]', '', text)
        
        # 1. 키워드 체크
        for keyword in self.trigger_keywords:
            clean_keyword = re.sub(r'[^a-zA-Z0-9가-힣]', '', keyword)
            if clean_keyword in clean_text:
                return ("KEYWORD", keyword)
        
        # 2. 질문/지시 패턴 체크 (정규식 지원)
        for pattern in self.question_patterns:
            # 패턴 자체가 포함되어 있는지 혹은 정규식으로 매칭되는지 확인
            clean_pattern = re.sub(r'[^a-zA-Z0-9가-힣]', '', pattern)
            if clean_pattern in clean_text:
                return ("QUESTION", pattern)
            
            # 실제 정규식 매칭 시도
            try:
                if re.search(pattern, text):
                    return ("QUESTION", pattern)
            except:
                continue
        
        return None




# === 테스트 실행 ===
if __name__ == "__main__":
    # Config 로드 및 시작
    config = load_config()
    ears = GhostEars(config)
    
    print("\n🚀 [STT 시스템 가동 (Queue Mode)]")
    print(f"🎯 감지할 키워드: {ears.trigger_keywords}")
    print("-" * 40)
    
    # 백그라운드 리스닝 시작
    if ears.start_listening():
        try:
            # 메인 스레드는 Queue 처리 담당
            for text in ears.process_queue():
                if text:
                    print(f"▶ 인식됨: {text}")
                    ears.save_to_log(text)
                    
                    trigger = ears.check_trigger(text)
                    if trigger:
                        trigger_type, matched = trigger
                        if trigger_type == "KEYWORD":
                            print(f"🚨 [긴급] 키워드 '{matched}' 감지!")
                        elif trigger_type == "QUESTION":
                            print(f"❓ [질문 감지] 질문 패턴 '{matched}' 감지됨")
        except KeyboardInterrupt:
            print("\n🛑 시스템 종료")
            if hasattr(ears, 'stopper'):
                ears.stopper(wait_for_stop=False)