import speech_recognition as sr
from faster_whisper import WhisperModel
import os
import time

class GhostEars:
    def __init__(self, device_index, model_size="large-v3"):
        print(f"--- 🎧 [GhostEars] 모델 로딩 중... ({model_size}) ---")
        # device="cuda"로 하면 GPU 사용, 없으면 "cpu"
        # compute_type="int8"은 CPU에서 속도 최적화
        try:
            self.model = WhisperModel(model_size, device="cuda", compute_type="int8")
            print("✅ 모델 로딩 완료! (준비 끝)")
        except Exception as e:
            print(f"❌ 모델 로딩 실패: {e}")
            
        self.device_index = device_index
        self.recognizer = sr.Recognizer()
        # 임시 오디오 파일명
        self.temp_filename = "temp_ghost_audio.wav"

    def listen_and_transcribe(self):
        """
        마이크(시스템 오디오)를 5초간 듣고 텍스트로 변환하여 리턴
        """
        try:
            with sr.Microphone(device_index=self.device_index, sample_rate=44100) as source:
                print("👂 [Listening] 듣는 중...")
                # 3~5초 정도 듣기 (너무 길면 반응 느려짐)
                audio_data = self.recognizer.listen(source, timeout=3, phrase_time_limit=5)
                
                # 1. 오디오 데이터를 임시 wav 파일로 저장 (Whisper는 파일 입력을 좋아함)
                with open(self.temp_filename, "wb") as f:
                    f.write(audio_data.get_wav_data())
                
                # 2. Whisper로 변환 (Transcribe)
                # beam_size=5: 정확도 높임
                segments, info = self.model.transcribe(self.temp_filename, beam_size=5, language="ko")
                
                # 3. 결과 합치기
                full_text = ""
                for segment in segments:
                    full_text += segment.text
                
                return full_text.strip()

        except sr.WaitTimeoutError:
            return None # 말 안 하면 패스
        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            return None

# --- 👇 테스트 실행 영역 (이 파일만 실행했을 때) ---
if __name__ == "__main__":
    # 아까 성공했던 Index 번호 (5번)
    MY_DEVICE_INDEX = 5 
    
    # 클래스 생성 (최초 1회 모델 로딩 - 시간 좀 걸림)
    ears = GhostEars(device_index=MY_DEVICE_INDEX)
    
    # 내 이름 설정 (트리거)
    MY_NAME = "개발" # '김개발', '학생' 등 설정
    
    print("\n🚀 [STT 시스템 가동] 유튜브 뉴스를 틀어보세요!")
    
    while True:
        text = ears.listen_and_transcribe()
        
        if text:
            print(f"▶ 인식됨: {text}")
            
            # 🔥 핵심 로직: 내 이름이 들릴 때만 반응
            if MY_NAME in text:
                print(f"🚨 [긴급] '{MY_NAME}' 호출 감지! -> GPT에게 답변 요청하세요!")
            elif "?" in text or "까" in text: # 질문형 문장 감지
                print(f"❓ [질문 감지] 교수님이 뭔가 물어보는 중...")
        else:
            # 침묵 중일 땐 CPU를 위해 살짝 쉼
            pass