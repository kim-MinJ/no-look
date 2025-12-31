import time
import asyncio
import os
import sys
from collections import deque

# ai/sound 폴더를 path에 추가
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "sound"))

from macro_bot import MacroBot
from zoom_automation import ZoomAutomator
from stt_core import GhostEars, load_config

async def run_auto_macro():
    print("🚀 [Zoom 자동 매크로 서비스] 가동 중... (맥락 이해 모드)")
    
    config = load_config()
    ears = GhostEars(config)
    bot = MacroBot()
    automator = ZoomAutomator()
    
    # 전략 1 & 2: 대화 기록을 저장할 바구니 (최근 10줄)
    history = deque(maxlen=10)
    
    # 전략 3: 짧게 끊긴 문장들을 하나로 합치기 위한 임시 버퍼
    sentence_buffer = []
    last_received_time = time.time()
    MERGE_THRESHOLD = 2.0  # 2초 이내의 말은 하나의 문장으로 인식 시도

    print("-" * 50)
    print(f"🎤 마이크 인덱스: {ears.device_index} (설정: {config['settings'].get('device_index')})")
    print(f"🧠 AI 모델: {bot.model.model_name if bot.model else 'None'}")
    print("💡 Enter: 전송 / Right Shift: 취소")
    print("-" * 50)

    if not ears.start_listening():
        return

    try:
        print("👂 소리를 듣고 있습니다... 설정을 시작합니다.")
        for text in ears.process_queue():
            if text:
                current_time = time.time()
                
                # 전략 3: 짧은 문장 병합 로직
                # 마지막 인식 후 시간이 짧게 지났으면 같은 문맥으로 판단하여 버퍼에 추가만 함
                if current_time - last_received_time < MERGE_THRESHOLD:
                    sentence_buffer.append(text)
                else:
                    # 시간이 꽤 지났으면 이전 버퍼를 기록에 넣고 새로 시작
                    if sentence_buffer:
                        merged_sentence = " ".join(sentence_buffer)
                        history.append(merged_sentence)
                    sentence_buffer = [text]
                
                last_received_time = current_time
                
                # 현재 처리 중인 (합쳐진) 문장
                current_processing_text = " ".join(sentence_buffer)
                print(f"\n▶ 인식(누적): {current_processing_text}")
                
                # 트리거 체크 (현재 누적된 문장에 트리거가 있는지 확인)
                trigger = ears.check_trigger(current_processing_text)
                
                if trigger:
                    trigger_type, matched = trigger
                    print(f"🎯 트리거 감지! ({trigger_type}: {matched})")
                    
                    # Gemini 답변 생성 (진짜 대화 기록 전체를 보냄)
                    print("🧠 맥락 분석 중...")
                    # history와 현재 버퍼를 합쳐서 보냄
                    full_context = list(history) + [current_processing_text]
                    suggestion = bot.get_suggestion(current_processing_text, full_context)
                    
                    if suggestion:
                        print(f"💡 추천 답변: {suggestion}")
                        print("👉 [Enter] 전송 / [Right Shift] 취소")
                        
                        automator.wait_for_user_confirmation(suggestion)
                        
                        # 전송 후에는 버퍼와 기록을 정리하여 다음 대화 준비
                        history.append(current_processing_text)
                        sentence_buffer = []
                    else:
                        print("⚠️ 답변 생성 실패")

    except KeyboardInterrupt:
        print("\n👋 서비스를 종료합니다.")
    finally:
        if hasattr(ears, 'stopper'):
            ears.stopper(wait_for_stop=False)

if __name__ == "__main__":
    asyncio.run(run_auto_macro())