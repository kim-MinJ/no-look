import speech_recognition as sr
import time
import audioop

def check_pulse():
    print("--- 🩺 오디오 신호 진단 도구 ---")
    
    # 1. 장치 목록 출력
    mics = sr.Microphone.list_microphone_names()
    for i, name in enumerate(mics):
        print(f"Index {i}: {name}")
        
    # 2. 번호 입력
    try:
        dev_index = int(input("\n👉 테스트할 장치 번호(VB-Cable Output 등)를 입력: "))
    except:
        return

    # 3. 신호 측정 Loop
    print(f"\n--- [Index {dev_index}] 신호 모니터링 시작 ---")
    print("유튜브를 틀어보세요! 숫자가 0에서 팍팍 튀어야 정상입니다.")
    
    r = sr.Recognizer()
    try:
        # VB-Cable 기본값인 44100으로 시도. 안되면 48000으로 수정 필요.
        with sr.Microphone(device_index=dev_index, sample_rate=44100) as source:
            print("🎤 장치 열림. 측정 중... (Ctrl+C로 종료)")
            
            while True:
                # 1초 분량이 아니라 아주 짧게(0.1초) 데이터를 가져옴
                buffer = source.stream.read(4096) 
                if not buffer: break
                
                # 소리 크기(RMS) 계산
                energy = audioop.rms(buffer, 2)
                
                # 시각화 (게이지 바)
                bar = "█" * (energy // 500) 
                print(f"Signal: {energy:5d} | {bar}")
                
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        print("팁: sample_rate를 48000으로 바꿔보거나, 장치 번호를 다시 확인하세요.")

if __name__ == "__main__":
    check_pulse()