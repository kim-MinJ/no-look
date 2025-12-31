import os
import google.generativeai as genai
from dotenv import load_dotenv

# .env 파일 위치를 명시적으로 로드하여 꼬임 방지
base_dir = os.path.dirname(os.path.abspath(__file__))
# ai 폴더 상위의 .env 파일을 찾습니다.
dotenv_path = os.path.normpath(os.path.join(base_dir, '..', '.env'))

# 기존 환경 변수를 무시하고 .env 파일의 내용을 강제로 덮어씁니다.
load_dotenv(dotenv_path=dotenv_path, override=True)

class MacroBot:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None
            print("⚠️ GEMINI_API_KEY not found in environment.")
        
        # 개인화 설정 로드 (stt_core의 load_config 활용)
        from stt_core import load_config
        self.config = load_config()

    def get_suggestion(self, current_text: str, history: list = None):
        """
        대화 맥락(history)과 개인화 설정을 바탕으로 답변 생성
        """
        if not self.model or not current_text.strip():
            return None

        # 개인화 정보 추출
        persona = self.config.get("personalization", {})
        user_role = persona.get("user_role", "회의 참가자")
        topic = persona.get("meeting_topic", "일반 회의")
        style = persona.get("speaking_style", "정중한 구어체")

        # 최근 대화 내용 구성
        context_str = ""
        if history:
            context_str = "\n".join([f"- {h}" for h in history[:-1]])

        prompt = f"""
        당신은 실시간 온라인 강의를 듣고 있는 '대학생'의 비서입니다.
        사용자가 강의 중에 잠시 비우거나 졸고 있을 때, 교수님의 질문이나 출석 확인에 대신 답할 수 있는 자연스러운 한국어 채팅 답변을 '단 한 문장' 생성하세요.

        [학생 정보]
        - 역할: {user_role}
        - 현재 수업: {topic}
        - 원하는 말투: {style}

        [최근 강의 흐름]
        {context_str if context_str else "(방금 강의 시작)"}

        [교수님의 마지막 말]
        "{current_text}"

        지침:
        1. **학생다운 반응**: "네 알겠습니다", "감사합니다", "잘 보입니다/들립니다" 등 학생이 수업 중에 주로 사용하는 자연스러운 표현을 쓰세요.
        2. **맥락 중시**: 교수님의 질문이 예/아니오 대답인지, 의견을 묻는 것인지 파악하세요.
        3. **극도의 간결함**: 튀지 않게 핵심만 말하세요. (최대 15자 이내)
        4. **답변 내용만**: 인사말이나 설명 없이 오직 채팅에 보낼 내용만 출력하세요.

        채팅 답변 제안:
        """
        
        try:
            response = self.model.generate_content(prompt)
            # 불필요한 공백, 따옴표, 줄바꿈 제거
            return response.text.strip().replace('"', '').replace('\n', ' ')
        except Exception as e:
            print(f"❌ Gemini API Error: {e}")
            return None

if __name__ == "__main__":
    # 테스트 코드
    bot = MacroBot()
    history_test = ["안녕하세요", "오늘 프로젝트 일정에 대해 논의해보죠", "준비되셨나요?"]
    current_test = "자기소개 부탁드립니다."
    print(f"과거 맥락:\n" + "\n".join(history_test))
    print(f"현재 입력: {current_test}")
    print(f"AI 추천 답변: {bot.get_suggestion(current_test, history_test)}")