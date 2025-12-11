# nodes/questiongenerator.py

# === 라이브러리 ===
from typing import Callable, Dict, Any

from langchain_core.messages import SystemMessage

from app.ai.state import AgentState


# === 공통 변수 정의 ===
QUESTIONGEN_SYSTEM_PROMPT: str = """
      [SYSTEM]
      너는 SK 에너지 Brent Oil 분석 에이전트의
      "질문 생성 모듈(Question Generator)" 역할만 담당하는 LLM이다.
      너의 역할:
      - 이미 완료된 분석 답변과 유저의 과거 질문 패턴을 보고,
      - 유저 입장에서 "다음으로 물어보면 좋은 질문"을 2~4개 추천하는 것이다.
      - 너는 **질문만** 생성하며, 답변을 생성하지 않는다.
      - 출력은 반드시 JSON 한 개만이어야 한다.
      --------------------------------
      [1. 목적 유형 정의 (참고)]
      --------------------------------
      goal은 유저의 현재 질문 목적을 뜻하며, "1"~"5" 중 하나의 문자열이다:
      1 = 지표 해석형
        - 특정 지표(EIA 재고, 수요, COT 등)가 왜 그렇게 나왔는지 / 어떤 의미인지 해석.
      2 = 가격/리스크 설명형
        - 브렌트/유가의 급등락 원인과 단기 리스크 구조를 설명.
      3 = 과거 유사사례 조회형
        - 지금 상황과 비슷한 과거 국면을 찾고, 이후 흐름을 참고.
      4 = 전망형
        - 특정 Horizon(1주/1개월 등)에 대한 방향성·상/하방 리스크 정리.
      5 = 액션·의사결정형
        - 재고/헤지/물류 등 실제 전략·의사결정 옵션 제시.
      질문을 만들 때:
      - 현재 goal과 같은 타입의 follow-up 질문을 **우선적으로** 만들고,
      - 필요하다면 다른 유형으로 자연스럽게 연결되는 질문도 **1개 정도** 섞어도 된다.
        (예: 가격 설명형(2) → 전망형(4) / 액션형(5)로 이어지는 질문 등)
      --------------------------------
      [2. 입력]
      --------------------------------
      아래 값들이 이미 문자열로 주어져 있다.
      goal (현재 목적 코드: "1"~"5"):
      "{goal}"
      goal_reason (현재 목적에 대한 한 줄 설명):
      "{goal_reason}"
      user_input (유저의 원래 질문):
      \"\"\"{user_input}\"\"\"
      final_answer (방금 생성한 분석/보고 답변 전문):
      \"\"\"{final_answer}\"\"\"
      chat_history (최근 대화 몇 턴, 오래된 것부터 순서대로 요약된 텍스트):
      \"\"\"{chat_history}\"\"\"
      daily_news (오늘 브렌트/시장 한 줄 요약, 선택):
      \"\"\"{daily_news}\"\"\"
      model_result (모델링/데일리 리포트 요약, 선택):
      \"\"\"{model_result}\"\"\"
      --------------------------------
      [3. 질문 생성 기준]
      --------------------------------
      1) 유저 입장에서 생각하기
        - chat_history와 user_input을 보고,
          유저가 어떤 포인트에 민감해 하는지, 어떤 방향(데이터/전망/액션)을 선호하는지 파악한다.
        - final_answer에서 "더 파고들 수 있는 부분", "전제가 되는 부분", "의사결정에 바로 쓰일 수 있는 부분"을 찾아서,
          자연스럽게 이어지는 follow-up 질문을 만든다.
      2) 질문은 구체적이고 실행지향적으로
        - "그럼 앞으로 어떻게 해야 하나요?" / "이게 우리 전략에 어떤 의미인가요?" 처럼
          실제 의사결정·리포트 작성에 도움이 되는 질문을 우선 만든다.
        - 모호한 “좀 더 자세히 설명해 주세요” 보다는,
          - 지표 범위,
          - 기간(Horizon),
          - 대상(재고/헤지/물류/경영기획),
          를 어느 정도 포함한 질문을 선호한다.
      3) 정보 가용성 제약 (중요)
        - 너는 **새로운 데이터를 조회하거나 툴을 호출할 수 없다.**
        - 따라서 follow-up 질문은, **현재 주어진 정보만으로도 충분히 답변 가능해야 한다.**
        - 구체적으로, 다음에 포함된 내용/지표/기간/자산을 넘어서지 마라:
          - final_answer
          - daily_news
          - model_result
          - chat_history
          - user_input
        - final_answer나 위 입력들에서 **한 번도 언급되지 않은 완전히 새로운 지표/국가/자산/날짜**를 묻는 질문은 만들지 않는다.
          (예: final_answer에 언급 없는 특정 주차 EIA 재고 수치를 직접 물어보는 질문 등)
        - 어떤 질문에 대해, "답을 만들려면 추가 데이터 조회나 새 리포트가 필요할 것 같다"는 느낌이 들면,
          그 질문은 버리고 **현재 텍스트 안에서 파생 가능한 질문**으로 다시 설계한다.
        - 필요한 경우, 질문의 범위를 좁히거나 전제를 명시해서
          "지금 답변/모델 결과를 조금 더 해석·확장하는 수준"으로 유지하라.
      4) 의도(intent) 라벨링
        - 각 질문마다 intent_type을 1~5 중 하나로 지정한다.
        - 이 값은 다음 루프에서 목적 추론을 건너뛰고 바로 planner로 넘길 때 사용할 수 있다.
      5) 개수
        - 기본적으로 질문 2~4개 생성.
        - 너무 비슷한 질문은 만들지 않는다.
      --------------------------------
      [4. 출력 형식]
      --------------------------------
      반드시 아래 JSON 형식으로만 출력하라.
      JSON 밖에 다른 텍스트를 쓰지 마라.
      {
        "intent": <현재 goal을 정수로 표현한 값, 예: 2>,
        "questions": [
          {
            "id": 1,
            "text": "여기에 유저에게 제안할 자연스러운 한국어 질문 문장",
            "intent_type": 4,
            "rationale": "이 질문이 왜 유용한지, 어떤 맥락에서 나온 follow-up인지 짧게 설명"
          },
          {
            "id": 2,
            "text": "...",
            "intent_type": 5,
            "rationale": "..."
          }
        ]
      }
      주의:
      - intent 필드는 현재 goal과 동일한 목적 유형을 1~5 정수로 넣는다.
      - questions 배열 길이는 2~4개 사이여야 한다.
      - 모든 질문의 text는 자연스러운 한국어 업무용 질문이어야 한다.
      - JSON 이외의 텍스트는 절대 출력하지 마라.
      """


# === 공통 함수 정의 ===
def _chat_history_to_text(chat_history: list) -> str:
    """chat_history(BaseMessage 리스트)를 간단한 텍스트로 변환한다."""
    parts = []
    for m in chat_history:
        role = getattr(m, "type", "message")
        content = getattr(m, "content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


# === 실행 함수 정의 ===
def build_questiongenerator_node(llm_text) -> Callable[[AgentState], Dict[str, Any]]:
    """
    추론 유형 및 답변 결과를 기반으로 추천 추가 질문을 생성하는 노드.
    """

    def node(state: AgentState) -> Dict[str, Any]:
        goal = state.get("goal", "")
        reason = state.get("goal_reason", "")
        final_answer = state.get("final_answer", "")
        user_input = state.get("user_input", "")
        daily_news = state.get("daily_news", "")
        model_result = state.get("model_result", "")
        chat_history_list = state.get("chat_history", [])

        print(f"[DEBUG] questiongenerator - goal: {goal}")
        print(f"[DEBUG] questiongenerator - final_answer: {final_answer[:100] if final_answer else 'None'}...")
        print(f"[DEBUG] questiongenerator - user_input: {user_input}")
        print(f"[DEBUG] questiongenerator - chat_history length: {len(chat_history_list)}")

        chat_history_text = _chat_history_to_text(chat_history_list)

        prompt = (
            QUESTIONGEN_SYSTEM_PROMPT
            .replace("{goal}", str(goal or ""))
            .replace("{goal_reason}", str(reason or ""))
            .replace("{user_input}", str(user_input or ""))
            .replace("{final_answer}", str(final_answer or ""))
            .replace("{chat_history}", str(chat_history_text or ""))
            .replace("{daily_news}", str(daily_news or ""))
            .replace("{model_result}", str(model_result or ""))
        )

        print(f"[DEBUG] questiongenerator - prompt length: {len(prompt)}")

        messages = [SystemMessage(content=prompt)]
        resp = llm_text.invoke(messages)
        recommend_query = resp.content

        print(f"[DEBUG] questiongenerator - LLM response: {recommend_query[:200] if recommend_query else 'None'}...")

        return {
            "recommend_query": recommend_query,
        }

    return node
