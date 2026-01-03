import os
import sys
from dotenv import load_dotenv

# Windows 인코딩 설정
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# .env 파일 위치를 명시적으로 로드하여 꼬임 방지
base_dir = os.path.dirname(os.path.abspath(__file__))
# ai/sound 폴더를 path에 추가하여 모듈 임포트 가능하게 함
sound_dir = os.path.join(base_dir, "sound")
if sound_dir not in sys.path:
    sys.path.append(sound_dir)

# ai 폴더 상위의 .env 파일을 찾습니다.
dotenv_path = os.path.normpath(os.path.join(base_dir, '..', '.env'))

# 기존 환경 변수를 무시하고 .env 파일의 내용을 강제로 덮어씁니다.
load_dotenv(dotenv_path=dotenv_path, override=True)

class MacroBot:
    def __init__(self):
        # EXAONE 모델 로드 (Shared Loader 사용)
        from exaone_loader import ExaoneLoader
        self.loader = ExaoneLoader()
        self.model = self.loader._model  # 호환성을 위해 유지하지만, 실제론 loader 사용
        
        # 개인화 설정 로드 (stt_core의 load_config 활용)
        from stt_core import load_config
        self.config = load_config()

    def get_suggestion(self, current_text: str, history: list = None):
        """
        대화 맥락(history) 및 개인화 설정을 바탕으로 답변 생성
        """
        if not self.model or not current_text.strip():
            return None

        # 개인화 정보 추출
        persona = self.config.get("personalization", {})
        user_role = persona.get("user_role", "회의 참가자")
        topic = persona.get("meeting_topic", "일반 회의")
        style = persona.get("speaking_style", "정중한 구어체")

        # 최근 대화 내용 구성 (최근 10개로 제한하여 성능 및 집중도 향상)
        recent_history = history[-10:] if history else []
        context_str = "\n".join([f"- {h}" for h in recent_history])

        prompt = f"""
        당신은 온라인 비대면 '실시간 강의'를 수강 중인 대학생의 AI 비서입니다.
        당신의 목표는 교수님의 질문이나 출석 확인 상황에서 학생이 직접 채팅하는 것 같은 '현실적이고 자연스러운 한국어' 답변을 '단 한 문장' 제안하는 것입니다.

        [학생 페르소나]
        - 역할: {user_role}
        - 현재 과목명: {topic}
        - 말투 성향: {style} (반드시 반영할 것)

        [답변 생성 지침]
        1. **상황 적합성**: 인사, 출석 대답, 긍정/부정 답변, 리액션 등 상황을 정확히 판단하세요.
        2. **극도의 자연스러움**: "넵!", "감사합니다 교수님", "잘 보여요", "이해됐습니다" 등 실제 대학생이 쓸법한 구어체를 사용하세요.
        3. **최소한의 길이**: 15자 이내의 단문으로 답변하세요.
        4. **결과만 출력**: 설명이나 인사말 없이 오직 전송할 채팅 답변 내용만 출력하세요.

        [상황별 답변 예시 (Few-shot)]
        질문: "다들 제 목소리 잘 들리나요?" -> 답변: "네, 잘 들립니다!"
        질문: "화면 공유된 거 보이시죠?" -> 답변: "네 잘 보입니다"
        질문: "지금까지 설명한 내용 이해되셨나요?" -> 답변: "네 이해됐습니다!"
        질문: "홍길동 학생 출석했나요?" -> 답변: "네, 출석했습니다."
        질문: "오늘 수업은 여기까지 하겠습니다. 질문 있나요?" -> 답변: "고생하셨습니다! 감사합니다."

        [현재 실시간 강의 맥락]
        {context_str if context_str else "(방금 강의 시작됨)"}

        [교수님의 마지막 말씀]
        "{current_text}"

        채팅 답변 제안:
        """
        
        try:
            # EXAONE Loader 사용
            response_text = self.loader.generate_content(prompt)
            # 불필요한 공백, 따옴표, 줄바꿈 제거
            return response_text.strip().replace('"', '').replace('\n', ' ')
        except Exception as e:
            print(f"❌ EXAONE Generation Error: {e}")
            return None

if __name__ == "__main__":
    # 테스트 코드
    bot = MacroBot()
    history_test = ["안녕하세요", "오늘 프로젝트 일정에 대해 논의해보죠", "준비되셨나요?"]
    current_test = "자기소개 부탁드립니다."
    print(f"과거 맥락:\n" + "\n".join(history_test))
    print(f"현재 입력: {current_test}")
    print(f"AI 추천 답변: {bot.get_suggestion(current_test, history_test)}")