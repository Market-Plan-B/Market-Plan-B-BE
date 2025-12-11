# app/ai/graph.py

# === 라이브러리 ===
from typing import Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver



from app.ai.models.llms import get_llm_text, get_llm_json
from app.ai.state import AgentState

from app.ai.nodes.interinferencer import build_interinferencer_node
from app.ai.nodes.planner import build_planner_node
from app.ai.nodes.toolquery import build_toolquery_node
from app.ai.nodes.answergenerator import build_answergenerator_node
from app.ai.nodes.questiongenerator import build_questiongenerator_node

from app.ai.tools.indicator_snapshot import run_indicator_snapshot
from app.ai.tools.news_rag import run_news_rag
from app.ai.tools.pattern_lookup import run_pattern_lookup
from app.ai.tools.graph_tool import run_graph_tool


# === 공통 함수 정의 ===
def _route_from_interinferencer(state: AgentState) -> str:
    """
    interinferencer 이후 라우팅 결정.
    user_input이 비어있거나 초기 추천 질문 요청이면 questiongenerator로,
    실제 분석 질문이면 planner로 이동.
    """
    user_input = state.get("user_input", "").strip()
    
    # 빈 입력이거나 초기 추천 질문 요청이면 questiongenerator로
    if not user_input:
        return "questiongenerator"
    
    # 실제 분석이 필요한 질문이면 planner로
    return "planner"


# === 실행 함수 정의 ===
def build_app(chroma_collection=None, checkpointer=None):
    """
    LangGraph StateGraph를 구성하고 컴파일된 앱을 반환한다.
    chroma_collection은 과거 버전 호환용 인자이며,
    현재 news_rag는 내부 chroma_service를 직접 사용한다.

    ✅ checkpointer를 외부에서 주입할 수 있게 수정
    """
    llm_text = get_llm_text()
    llm_json = get_llm_json()

    # 툴 매핑 정의
    tools = {
        "indicator_snapshot": run_indicator_snapshot,
        "news_rag": lambda **kwargs: run_news_rag.invoke(kwargs),
        "pattern_lookup": run_pattern_lookup,
        "graph_tool": run_graph_tool,
    }

    graph = StateGraph(AgentState)

    # 노드 정의
    graph.add_node("interinferencer", build_interinferencer_node(llm_json))
    graph.add_node("planner", build_planner_node(llm_json))
    graph.add_node("toolquery", build_toolquery_node(llm_text, tools))
    graph.add_node("answergenerator", build_answergenerator_node(llm_text))
    graph.add_node("questiongenerator", build_questiongenerator_node(llm_text))

    # 플로우 정의
    graph.set_entry_point("interinferencer")

    graph.add_conditional_edges(
        "interinferencer",
        _route_from_interinferencer,
        {
            "planner": "planner",
            "questiongenerator": "questiongenerator",
        },
    )

    graph.add_edge("planner", "toolquery")
    graph.add_edge("toolquery", "answergenerator")
    graph.add_edge("answergenerator", "questiongenerator")
    graph.add_edge("questiongenerator", END)

    # ✅ checkpointer 연결
    if checkpointer is None:
        checkpointer = MemorySaver()

    app = graph.compile(checkpointer=checkpointer)
    return app


def run_chat_round(
    app,
    prev_state: AgentState,
    user_input: str,
) -> AgentState:
    """
    간단한 한 턴 실행 헬퍼.
    prev_state와 user_input을 넣고, 새로운 상태를 반환한다.
    (checkpointer 없이 단일 프로세스 안에서만 사용할 때용)
    """
    # 유저 메시지 추가
    chat_history = prev_state.get("chat_history", [])
    if user_input:
        chat_history = chat_history + [HumanMessage(content=user_input)]

    state_update: AgentState = AgentState(
        **prev_state,
        user_input=user_input,
        chat_history=chat_history,
    )

    new_state: Dict[str, Any] = app.invoke(state_update)

    # 최종 답변이 있다면 히스토리에 추가
    final_answer = new_state.get("final_answer")
    if final_answer:
        new_state["chat_history"] = new_state.get("chat_history", []) + [
            AIMessage(content=final_answer)
        ]

    return new_state  # type: ignore[return-value]
