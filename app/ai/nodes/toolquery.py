# app/ai/nodes/toolquery.py

# === 라이브러리 ===
from typing import Callable, Dict, Any, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.state import AgentState


# === 공통 프롬프트 정의 ===
TOOLQUERY_SUMMARY_SYSTEM_PROMPT: str = """
너는 브렌트 유가 분석 에이전트의 '툴 결과 통합 요약기'이다.

[역할]
- indicator_snapshot, news_rag, pattern_lookup 등의 원시 결과(raw)를 입력으로 받아
  브렌트 가격 해석에 필요한 핵심 내용만 한국어로 정리한다.
- 단, 유저가 원하는 출력 형식(표/리스트/나열/문단/그래프)을 최대한 그대로 따른다.

[출력 형식 규칙]
아래는 user_input 문장 안의 키워드에 따른 출력 형식 가이드이다.
LLM 너는 user_input을 참고하여 가장 적절한 형식을 선택하라.

1) "표", "table", "표로", "테이블로" 등의 표현이 포함되면
   → 표 형태로 요약한다.
   - Markdown 표 형식 사용 (예: | 컬럼1 | 컬럼2 | ...)
   - 기본 추천 컬럼:
     - 툴 이름(tool)
     - 핵심 내용(summary)
     - 방향성 또는 영향(impact: 상승/하락/리스크 등)

2) "리스트", "bullet", "나열", "정리해줘" 등의 표현이 포함되면
   → 리스트(불릿) 형태로 요약한다.
   - 각 툴별로 bullet 형태로 주요 포인트만 정리
   - 예:
     - indicator_snapshot: 최근 브렌트 가격은 OOO, 재고는 OOO 경향
     - news_rag: OOO 관련 뉴스가 다수, 날짜/점수(랭킹)·내용 중심 요약
     - pattern_lookup: 해당 클러스터에서 과거에 가격이 어떻게 반응했는지

3) "그래프", "차트", "chart", "시각화", "plot" 등의 표현이 포함되면
   → 그래프용 JSON 스펙을 추가로 생성한다.

   3-1) 기본 원칙
   - 우선 필요한 경우, 한국어로 간단한 설명을 먼저 제공할 수 있다.
   - 그 다음 줄부터는 **Vue/Chart.js에서 바로 쓸 수 있는 JSON 객체 하나만** 출력할 수 있다.
   - 이 JSON 구조는 아래 형식을 따른다.

   예시 형식:
   {
     "labels": ["1월", "2월", "3월", "4월"],
     "datasets": [
       {
         "label": "매출액",
         "data": [120, 200, 150, 300],
         "borderColor": "#36A2EB",
         "borderWidth": 2
       }
     ]
   }

   3-2) JSON 생성 규칙
   - labels:
     - 보통 x축에 해당하는 값들(예: 날짜 리스트, 월 리스트, 구간 이름 등)을 문자열 배열로 넣는다.
     - 예: ["2025-11-01", "2025-11-02", ...] 또는 ["1주차", "2주차", ...]
   - datasets:
     - 하나 이상의 데이터 시리즈를 배열로 넣는다.
     - 각 시리즈는 다음 필드를 가질 수 있다.
       - "label": "브렌트 종가", "재고 변화", "스프레드" 등 데이터 이름
       - "data": [숫자, 숫자, ...]  → labels와 길이가 맞도록 숫자 배열로 구성
       - "borderColor": "#36A2EB" 등  → 단순 색상 코드(필요하면 지정)
       - "borderWidth": 2 등  → 선 굵기(옵션)
   - indicator_snapshot 결과에 날짜별 시계열(price_timeseries 등)이 있다면
     → 해당 날짜를 labels로, 브렌트/WTI 종가 등의 시계열을 data로 사용하는 것을 우선 고려한다.
   - pattern_lookup 결과에 구간별 값이 있다면
     → 구간/섹션 이름을 labels로, 해당 값(증감률 등)을 data로 사용할 수 있다.
   - 사실/숫자를 새로 만들어내지 말고,
     항상 입력으로 주어진 결과 안의 값, 혹은 그로부터 합리적으로 계산 가능한 값만 사용한다.

   3-3) 응답 형태 선택
   - 유저가 "그래프 JSON만 줘", "차트용 데이터만" 등의 표현을 사용하면:
     → 자연어 설명 없이 **순수 JSON 객체 하나만** 반환해도 된다.
   - 그 외에는:
     → 한국어 설명 + JSON을 함께 줄 수 있다.

4) 위 표현이 없으면
   → 기본 문단/섹션 요약 형태를 사용한다.
   - 가능한 순서:
     [지표 스냅샷] → indicator_snapshot 기반
     [뉴스 요약] → news_rag 기반
     [클러스터/패턴 요약] → pattern_lookup 기반
   - 전체 5~10줄 정도로 압축

[입력 데이터의 의미(참고용)]
- indicator_snapshot_result (dict 예상)
  - 최근 브렌트/WTI 가격 시계열과 최신 값,
  - EIA 재고·생산·정제 가동률,
  - COT 포지션 요약 등이 포함될 수 있다.

- news_rag_result (list 예상)
  - 뉴스 관련 툴(run_news_rag)의 결과 리스트.
  - 각 항목은 semantic 모드 또는 SQL-only 모드에 따라 다음과 같은 필드를 가질 수 있다.
    - title: 뉴스 제목
    - content: 뉴스 본문 (있으면)
    - summary: 뉴스 요약 (있으면)
    - published_at: 뉴스 날짜 (YYYY-MM-DD 또는 datetime)
    - source_score: 점수/랭킹 지표 (있으면, 예: 중요도/신뢰도 등)
    - distance: 임베딩 유사도 거리 (semantic 모드에서 사용, 값이 작을수록 더 유사)
    - url: 기사 링크 (있으면)
  - 즉,
    - semantic 모드일 때는 "내용이 비슷한 뉴스 묶음"을,
    - SQL-only 모드일 때는 "특정 기간/조건에서 상위 랭킹 뉴스 리스트"를 의미한다.

- pattern_lookup_result (dict 예상)
  - 특정 클러스터 ID에 대해,
    BRENT / EIA / COT 등 섹션별로
    정형 지표가 어떻게 반응했는지(상승/하락, 증감, 확대/축소 등)에 대한 패턴 정보가 들어 있다.

[요약 방식]
- 브렌트 가격/리스크 해석에 직접 도움이 되는 정보 위주로 정리한다.
- 가능한 한 다음 관점에서 압축한다.
  - 가격 수준 및 최근 변화(상승/하락, 변동성 확대/축소 등)
  - 재고·수요·생산 등 펀더멘털의 방향성
  - COT 포지션(순매수/순매도)의 변화
  - 주요 뉴스 이벤트(날짜, 점수/랭킹, 핵심 이슈)
    - semantic 모드 결과: 어떤 이슈/뉴스 내용이 많이 등장하는지
    - SQL-only 모드 결과: 어떤 뉴스가 높은 점수 또는 최근 날짜 기준 상위에 있는지
  - 과거 패턴(특정 클러스터에서 가격/지표가 보이는 전형적인 반응)
- 사실/숫자를 새로 만들어내지 말고,
  항상 입력으로 주어진 결과 안의 내용만 바탕으로 추론/요약한다.

[주의 사항]
- 툴 결과가 비어 있거나 거의 없으면,
  "참고 가능한 데이터가 제한적"이라는 식으로 간단히 언급하되,
  억지로 내용을 채우지 않는다.
- 최종 출력에는 System/Human 프롬프트를 그대로 반복하지 말고,
  요약 결과만 출력한다.
"""


# === 공통 함수 정의 ===
def _execute_tool_step(
    step: Dict[str, Any],
    tools: Dict[str, Callable[..., Any]],
) -> Any:
    """단일 툴 스텝을 실행한다."""
    tool_name = step.get("tool")
    args = step.get("args", {}) or {}
    tool_fn = tools[tool_name]
    return tool_fn(**args)


def _summarize_tool_results(
    llm_text,
    results: Dict[str, Any],
    user_input: str,
) -> str:
    """툴 결과들을 LLM으로 간단히 요약한다."""
    # 툴이 하나도 실행되지 않은 경우 방어
    if not results:
        messages = [
            SystemMessage(content=TOOLQUERY_SUMMARY_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"[user_input]\n{user_input}\n\n"
                    "[tool_results]\n"
                    "툴 실행 결과가 없습니다. 참고 가능한 데이터가 거의 없습니다."
                )
            ),
        ]
        resp = llm_text.invoke(messages)
        return resp.content

    content_lines: List[str] = []

    # 같은 툴이 여러 번 실행된 경우 리스트로 들어오므로 모두 펼쳐서 넣어줌
    for name, value in results.items():
        if isinstance(value, list):
            for idx, v in enumerate(value, start=1):
                content_lines.append(f"[{name} #{idx} 결과]\n{str(v)}\n")
        else:
            content_lines.append(f"[{name} 결과]\n{str(value)}\n")

    content = "\n".join(content_lines)

    messages = [
        SystemMessage(content=TOOLQUERY_SUMMARY_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"[user_input]\n{user_input}\n\n"
                f"[tool_results]\n{content}"
            )
        ),
    ]
    resp = llm_text.invoke(messages)
    return resp.content


# === 실행 함수 정의 ===
def build_toolquery_node(
    llm_text,
    tools: Dict[str, Callable[..., Any]],
) -> Callable[[AgentState], Dict[str, Any]]:
    """
    planner가 만든 tool_plan에 따라 여러 툴을 실행하고,
    중간 요약(intermediate_answer)와 raw 결과(tool_results)를 반환한다.

    - state["tool_plan"]: planner가 만든 plan(JSON 리스트)
      예: [{"tool": "indicator_snapshot", "args": {...}}, ...]
    - tools: 실제 파이썬 함수들이 들어 있는 dict
      예: {"indicator_snapshot": indicator_snapshot_fn, ...}
    """

    def node(state: AgentState) -> Dict[str, Any]:
        plan = state.get("tool_plan", []) or []

        # 같은 툴을 여러 번 호출할 수 있으므로, 리스트로 누적
        all_results: Dict[str, List[Any]] = {}

        for step in plan:
            name = step.get("tool")
            if not name or name not in tools:
                # 정의되지 않은 툴은 무시
                continue
            result = _execute_tool_step(step, tools)

            if name not in all_results:
                all_results[name] = []
            all_results[name].append(result)

        summary = _summarize_tool_results(
            llm_text=llm_text,
            results=all_results,
            user_input=state.get("user_input", "") or "",
        )

        # 최신 한 개(기존 필드용) + 전체 리스트(비교용) 같이 제공
        indicator_list = all_results.get("indicator_snapshot", [])
        news_list = all_results.get("news_rag", [])
        pattern_list = all_results.get("pattern_lookup", [])
        graph_list = all_results.get("graph_tool", [])

        indicator_latest = indicator_list[-1] if indicator_list else {}
        news_latest = news_list[-1] if news_list else []
        pattern_latest = pattern_list[-1] if pattern_list else {}
        graph_latest = graph_list[-1] if graph_list else None

        return {
            # 툴별 전체 결과 (리스트 형태)
            "tool_results": all_results,

            # 기존 인터페이스 유지: "마지막 한 번" 결과
            "indicator_snapshot_result": indicator_latest,
            "news_rag_result": news_latest,
            "pattern_lookup_result": pattern_latest,

            # 새로 추가: 전체 호출 결과 리스트
            "indicator_snapshot_results": indicator_list,
            "news_rag_results": news_list,
            "pattern_lookup_results": pattern_list,

            # 그래프용 결과
            "graph_tool": graph_latest,
            "graph_tool_results": graph_list,

            "intermediate_answer": summary,
        }

    return node
