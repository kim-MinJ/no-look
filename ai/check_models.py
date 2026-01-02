import os
import google.generativeai as genai
from dotenv import load_dotenv

# .env 파일 로드
base_dir = os.path.dirname(os.path.abspath(__file__))
# 경로가 맞는지 확인 필요 (..가 필요한지 체크)
dotenv_path = os.path.normpath(os.path.join(base_dir, '..', '.env')) 
load_dotenv(dotenv_path=dotenv_path, override=True)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print(f"❌ API 키를 찾을 수 없습니다. (경로: {dotenv_path})")
else:
    genai.configure(api_key=api_key)
    print("🔍 사용 가능한 모델 리스트:")
    try:
        found_flash = False
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
                if 'flash' in m.name:
                    found_flash = True
        
        print("-" * 20)
        if not found_flash:
            print("⚠️ 'flash' 모델이 안 보입니다! 라이브러리 업데이트가 필요합니다.")
            print("👉 터미널 실행: pip install -U google-generativeai")
            
    except Exception as e:
        print(f"❌ 에러 발생: {e}")