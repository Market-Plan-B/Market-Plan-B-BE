# === 라이브러리 ===
import os
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


# === 공통 변수 정의 ===
load_dotenv()
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL_NAME: str = "gpt-4o"


# === 공통 함수 정의 ===
def _build_llm(model: str, json_mode: bool) -> ChatOpenAI:
    """기본 LLM 생성 함수. json_mode가 True면 JSON 포맷 강제."""
    if json_mode:
        return ChatOpenAI(
            model=model,
            temperature=0.0,
            api_key=OPENAI_API_KEY,
            response_format={"type": "json_object"},
        )
    else:
        return ChatOpenAI(
            model=model,
            temperature=0.0,
            api_key=OPENAI_API_KEY,
        )


# === 실행 함수 정의 ===
def get_llm_text() -> ChatOpenAI:
    """일반 텍스트 응답용 LLM."""
    return _build_llm(DEFAULT_MODEL_NAME, json_mode=False)


def get_llm_json() -> ChatOpenAI:
    """JSON 구조화 응답용 LLM."""
    return _build_llm(DEFAULT_MODEL_NAME, json_mode=True)
