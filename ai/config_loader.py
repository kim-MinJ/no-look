# ai/config_loader.py
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


APP_NAME = "No-Look"


def _dev_config_path() -> Path:
    # 개발환경 기본: ai/sound/config.json
    base_dir = Path(__file__).resolve().parent
    return base_dir / "sound" / "config.json"


def _user_config_path() -> Path:
    # 배포/권장: %APPDATA%/No-Look/config.json
    appdata = os.getenv("APPDATA")
    if appdata:
        user_dir = Path(appdata) / APP_NAME
    else:
        user_dir = Path.home() / f".{APP_NAME.lower()}"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "config.json"


def default_config() -> Dict[str, Any]:
    # ✅ server.py ConfigPayload( triggers/personalization/settings/actions )에 맞춰서 기본값 제공
    return {
        "triggers": {
            "keywords": [],
            "question_patterns": ["?"],
        },
        "personalization": {
            "user_role": "회의 참가자",
            "meeting_topic": "일반 회의",
            "speaking_style": "정중한 구어체",
        },
        "settings": {
            "device_index": 0,
            "model_size": "medium",
            "language": "ko",
            "sample_rate": 48000,
        },
        "actions": {
            "auto_send_enabled": False,
        },
    }


def get_config_path() -> Path:
    """
    - 개발환경에서는 ai/sound/config.json을 우선 사용(있으면)
    - PyInstaller(또는 dev 파일이 없거나 쓰기 어려운 경우)에는 user config 사용
    - 환경변수 NOLOOK_CONFIG_PATH가 있으면 그걸 최우선
    """
    env = os.getenv("NOLOOK_CONFIG_PATH")
    if env:
        return Path(env).resolve()

    dev = _dev_config_path()
    if dev.exists():
        return dev

    return _user_config_path()


def ensure_config_exists() -> Path:
    cfg_path = get_config_path()

    if cfg_path.exists():
        return cfg_path

    # dev 경로가 없으면 user 경로에 생성
    if cfg_path == _dev_config_path():
        # dev 경로가 없는데 dev 경로를 쓰려는 상황이면 user로 생성
        cfg_path = _user_config_path()

    cfg_path.write_text(json.dumps(default_config(), ensure_ascii=False, indent=4), encoding="utf-8")
    return cfg_path


def load_config() -> Dict[str, Any]:
    cfg_path = ensure_config_exists()
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        # 깨졌으면 복구
        cfg = default_config()
        save_config(cfg)
        return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    cfg_path = ensure_config_exists()
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")


def get_transcript_path() -> Path:
    # ✅ [Developer Fix] 로그 확인 편의를 위해 프로젝트 폴더(ai/sound/transcript.txt)에 저장
    base_dir = Path(__file__).resolve().parent
    sound_dir = base_dir / "sound"
    sound_dir.mkdir(parents=True, exist_ok=True)
    return sound_dir / "transcript.txt"
