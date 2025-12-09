# === 라이브러리 ===
from typing import TypedDict, List, Dict, Any
from typing_extensions import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# === 실행 함수 정의 ===
class AgentState(TypedDict, total=False):
    # ===== 입력 / 컨텍스트 =====
    user_input: str                      # 사용자 질문 텍스트
    daily_news: str                      # 오늘 브렌트 관련 뉴스 요약
    model_result: str                    # 브렌트 예측 + XAI JSON 문자열
    first_start: bool                    # 첫 실행 여부 플래그
    daily_report: str                    # daily_report HTML/텍스트
    chat_history: Annotated[
        List[BaseMessage],
        add_messages,
    ]

    # ===== 목적 / 플랜 =====
    goal: str                            # 목적 추론 유형
    goal_reason: str                     # 목적 유형 선정 이유
    tool_plan: List[Dict[str, Any]]      # 툴 호출 계획 리스트

    # ===== 툴 결과 =====
    indicator_snapshot_result: Dict[str, Any]      # 정형 지표 스냅샷 결과(마지막 1개)
    news_rag_result: List[Dict[str, Any]]          # 유사 뉴스 RAG 결과(마지막 1개 호출분)
    pattern_lookup_result: Dict[str, Any]          # 클러스터 패턴 조회 결과(마지막 1개)
    tool_results: Dict[str, Any]                   # 전체 툴 raw 결과 모음

    # (toolquery에서 이미 내려주는 경우를 위한 확장 필드들)
    indicator_snapshot_results: List[Dict[str, Any]]  # indicator_snapshot 전체 호출 리스트
    news_rag_results: List[List[Dict[str, Any]]]      # news_rag 전체 호출 리스트
    pattern_lookup_results: List[Dict[str, Any]]      # pattern_lookup 전체 호출 리스트

    # ===== 답변 / 추천 질문 =====
    intermediate_answer: str             # 툴 결과 중간 요약 텍스트
    final_answer: str                    # 최종 답변 텍스트
    recommend_query: str                 # 추천 후속 질문 텍스트


def initial_state(
    user_input: str = "",
    daily_news: str = "",
    model_result: str = "",              # 예측 + XAI JSON 문자열
    daily_report: str = "",
    first_start: bool = True,
) -> AgentState:
    """그래프 시작 시 사용할 기본 상태 생성."""
    return AgentState(
        user_input=user_input,
        daily_news=daily_news,
        model_result=model_result,
        daily_report=daily_report,
        first_start=first_start,
        chat_history=[],
    )
