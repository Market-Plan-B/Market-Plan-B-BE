# app/ai/test_main.py

from typing import Any
import os
import json
import joblib

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.ai.graph import build_app
from app.ai.state import AgentState, initial_state

# --- main.py 상단에서 쓰던 서비스 함수들 import ---
from app.ai.services.brent_data_pipeline import build_full_dataset
from app.ai.services.unstructured_refine import unstructure_refine
from app.ai.services.pipeline_inference import run_inference
from app.ai.services.unstructured_summary import daily_news_data

# ✅ ChromaDB 서비스 import
from app.services.chroma_service import chroma_service

# ---------------------------------------------------------------------
# 토글: True → 에이전트만 가볍게 테스트 (모델링/크롤 파이프라인 생략)
#       False → 전체 파이프라인 (데이터셋 + XAI + 예측까지 모두 수행)
# ---------------------------------------------------------------------
AGENT_TEST = False


# === main.py 상단 로직과 동일한 helper들 ===

def _db_load() -> Any:
    """
    main.py의 db_load와 동일한 동작:
    - app/ai/repository/data/news 폴더에서 임의의 뉴스 파일 하나 읽어서 JSON 반환
    """
    print("[STEP-DB] 뉴스 파일 로드 시작", flush=True)
    load_path = "app/ai/repository/data/news"

    print(f"[STEP-DB] 디렉토리 확인: {load_path}", flush=True)
    files = [
        f
        for f in os.listdir(load_path)
        if os.path.isfile(os.path.join(load_path, f))
    ]
    print(f"[STEP-DB] 발견된 파일 개수: {len(files)}", flush=True)

    if not files:
        raise FileNotFoundError(f"{load_path} 에 뉴스 파일이 없습니다.")

    first_file = files[0]
    file_path = os.path.join(load_path, first_file)
    print(f"[STEP-DB] 사용할 파일: {first_file}", flush=True)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("[STEP-DB] JSON 로드 완료", flush=True)
    return data


def _daily_news(raw_news: Any):
    """
    main.py의 daily_news 함수와 동일하게 daily_news_data 래핑 +
    ✅ 생성된 embedded_news.json / 뉴스 임베딩을 ChromaDB에 적재.
    """
    print("[STEP-NEWS] daily_news_data 시작", flush=True)
    news = daily_news_data(raw_news)
    print("[STEP-NEWS] daily_news_data 완료", flush=True)

    # ✅ ChromaDB 적재
    try:
        print("[STEP-CHROMA] Chroma DB 적재 시작", flush=True)
        embedded_path = "data/embedded_news.json"

        if os.path.exists(embedded_path):
            # embedded_news.json 파일이 있으면 그 내용을 기준으로 적재
            print(f"[STEP-CHROMA] 파일에서 임베딩 로드: {embedded_path}", flush=True)
            with open(embedded_path, "r", encoding="utf-8") as f:
                embedded_news = json.load(f)
            inserted = chroma_service.add_news_embeddings(embedded_news)
        else:
            # 혹시 파일이 없으면 메모리상의 news 리스트로 적재
            print("[STEP-CHROMA] embedded_news.json 없음 → 메모리 객체(news)로 적재", flush=True)
            inserted = chroma_service.add_news_embeddings(news)

        print(f"[STEP-CHROMA] Chroma DB 적재 완료: {inserted}개 문서", flush=True)
    except Exception as e:
        print(f"[STEP-CHROMA] Chroma DB 적재 실패: {e}", flush=True)

    return news


def _daily_modeling(news_list):
    """
    main.py의 daily_modeling과 동일한 파이프라인:
    - build_full_dataset → unstructure_refine → run_inference
    - output:
      {
        "prediction": {
          "pred_return": ...,
          "today_close": ...,
          "predicted_next_close": ...
        },
        "xai": ...
      }
    """
    print("[STEP-MODEL] 브렌트 모델링 파이프라인 시작", flush=True)

    print("[STEP-MODEL-1] build_full_dataset(news=news_list) 호출", flush=True)
    df0, news_cluster = build_full_dataset(news=news_list)
    print(
        "[STEP-MODEL-1] build_full_dataset 완료 (df0.shape="
        f"{getattr(df0, 'shape', 'unknown')})",
        flush=True,
    )

    print("[STEP-MODEL-2] unstructure_refine(df0) 호출", flush=True)
    df1 = unstructure_refine(df0)
    print(
        "[STEP-MODEL-2] unstructure_refine 완료 (df1.shape="
        f"{getattr(df1, 'shape', 'unknown')})",
        flush=True,
    )

    print("[STEP-MODEL-3] run_inference(news_list, df=df1) 호출", flush=True)
    output = run_inference(news_list=news_list, df=df1)
    print("[STEP-MODEL-3] run_inference 완료", flush=True)

    pred = output.get("prediction", {})
    print(f"[STEP-MODEL-3] prediction 키 확인: {list(pred.keys())}", flush=True)

    print("[STEP-MODEL] 브렌트 모델링 파이프라인 종료", flush=True)
    return output


# === 유틸 함수 ===
def print_intro() -> None:
    """CLI 안내 메시지 출력."""
    print("=" * 60, flush=True)
    print(" 브렌트 챗봇 CLI 테스트 (LangSmith 연동)", flush=True)
    print(f"  - 모드: {'AGENT_TEST(경량)' if AGENT_TEST else 'FULL_PIPELINE'}", flush=True)
    print("  - 종료: exit / quit / q", flush=True)
    print("=" * 60, flush=True)


def print_turn_result(state: AgentState) -> None:
    """한 턴 결과(답변, 추천 질문) 출력."""
    final_answer = state.get("final_answer", "")
    recommend_query = state.get("recommend_query", "")

    print("[DEBUG] print_turn_result 호출", flush=True)

    if final_answer:
        print("\n[Agent 답변]", flush=True)
        print(final_answer, flush=True)

    if recommend_query:
        print("\n[Agent 추천 질문]", flush=True)
        print(recommend_query, flush=True)
        print(flush=True)


def _load_daily_report(path: str = "daily_report.html") -> str:
    """
    main.py에서 생성한 daily_report.html을 읽어서 문자열로 반환.
    파일이 없으면 빈 문자열 반환.
    """
    print(f"[STEP-REPORT] daily_report 로드 시도: {path}", flush=True)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        print(
            f"[STEP-REPORT] daily_report 로드 성공: length={len(content)}",
            flush=True,
        )
        return content
    except FileNotFoundError:
        print(f"[STEP-REPORT] daily_report 파일 없음: {path}", flush=True)
        return ""


# === 실행 함수 ===
def main() -> None:
    """브렌트 챗봇 CLI + LangSmith 트레이싱 진입점."""
    print("[DEBUG] test_main.main() 시작", flush=True)
    print(f"[DEBUG] AGENT_TEST 모드: {AGENT_TEST}", flush=True)

    print("[DEBUG] dotenv 로딩 시작", flush=True)
    load_dotenv()
    print("[DEBUG] dotenv 로딩 완료", flush=True)

    # LangSmith + LangGraph checkpointer용 설정
    print("[DEBUG] RunnableConfig 생성", flush=True)
    config = RunnableConfig(
        configurable={
            "session_id": "cli-brent-test",  # LangSmith용
            "thread_id": "cli-brent-test",   # ✅ LangGraph checkpointer용 (중요)
        },
        tags=["cli", "brent-agent"],
    )

    print("[DEBUG] LangGraph app 빌드 시작 (build_app 호출)", flush=True)
    # news_rag가 내부에서 chroma_service를 직접 쓰도록 구현되어 있다면 인자 없이 호출
    app = build_app()
    print("[DEBUG] LangGraph app 빌드 완료", flush=True)

    # 1) daily_report 처리
    if AGENT_TEST:
        print(
            "[DEBUG] AGENT_TEST=True → daily_report 생략, 빈 문자열 사용",
            flush=True,
        )
        daily_report = ""
    else:
        print("[DEBUG] daily_report.html 로드 단계 시작", flush=True)
        daily_report = _load_daily_report("daily_report.html")
        print("[DEBUG] daily_report.html 로드 단계 종료", flush=True)

    # 2) 모델링 / 뉴스 파이프라인
    if AGENT_TEST:
        print(
            "[DEBUG] AGENT_TEST=True → 뉴스/모델 파이프라인 생략",
            flush=True,
        )
        predicted_next_close = 0.0

        # ✅ 테스트 모드에서도 모델 결과를 JSON 구조로 맞춰줌
        model_payload = {
            "prediction": {
                "predicted_next_close": predicted_next_close,
            },
            "xai": {},
        }
        model_result = json.dumps(model_payload, ensure_ascii=False)
        daily_news = "테스트 모드: 임시 뉴스 데이터입니다."
    else:
        print("[DEBUG] 뉴스/모델 파이프라인 시작", flush=True)

        print("[DEBUG] _db_load() 호출", flush=True)
        raw_news = _db_load()
        print("[DEBUG] _db_load() 완료", flush=True)

        print("[DEBUG] _daily_news(raw_news) 호출", flush=True)
        news_list = _daily_news(raw_news)
        print("[DEBUG] _daily_news(raw_news) 완료", flush=True)

        print("[DEBUG] _daily_modeling(news_list) 호출", flush=True)
        modeling_output = _daily_modeling(news_list)
        print("[DEBUG] _daily_modeling(news_list) 완료", flush=True)

        print("[DEBUG] predicted_next_close + XAI 추출 시작", flush=True)
        prediction_block = modeling_output.get("prediction", {}) or {}
        xai_block = modeling_output.get("xai", {})  # ✅ XAI 같이 사용

        predicted_next_close = prediction_block.get("predicted_next_close", None)
        print(f"[DEBUG] predicted_next_close = {predicted_next_close}", flush=True)
        print(
            f"[DEBUG] XAI type / keys = "
            f"{type(xai_block)} / "
            f"{list(xai_block.keys()) if isinstance(xai_block, dict) else 'N/A'}",
            flush=True,
        )

        # ✅ 예측 + XAI를 하나의 JSON 문자열로 state에 전달
        model_payload = {
            "prediction": prediction_block,
            "xai": xai_block,
        }
        model_result = json.dumps(model_payload, ensure_ascii=False)

        daily_news = "오늘 브렌트 관련 주요 뉴스와 XAI 결과가 반영된 상태입니다."

    print("[DEBUG] initial_state 생성 시작", flush=True)
    state: AgentState = initial_state(
        daily_news=daily_news,
        model_result=model_result,  # ✅ 예측 + XAI JSON
        daily_report=daily_report,
        first_start=True,
    )
    print("[DEBUG] initial_state 생성 완료", flush=True)

    print_intro()

    # --- 1) 첫 턴: 유저 입력 없이 목적 추론 + 추천 질문만 실행 ---
    print("[DEBUG] 첫 턴 app.invoke 호출 (first_start=True)", flush=True)
    state = app.invoke(state, config=config)  # type: ignore[assignment]
    print("[DEBUG] 첫 턴 app.invoke 완료", flush=True)
    print_turn_result(state)

    # --- 2) 이후부터는 사용자 입력 기반 대화 ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[DEBUG] 입력 종료 신호 감지, 프로그램 종료", flush=True)
            print("종료합니다.", flush=True)
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("[DEBUG] 종료 명령 입력 감지", flush=True)
            print("종료합니다.", flush=True)
            break

        print(f"[DEBUG] 사용자 입력 수신: {user_input}", flush=True)

        invoke_state: AgentState = {
            "user_input": user_input,
            "first_start": False,
            "chat_history": [HumanMessage(content=user_input)],
        }

        print("[DEBUG] 다음 턴 app.invoke 호출 (first_start=False)", flush=True)
        state = app.invoke(invoke_state, config=config)  # type: ignore[assignment]
        print("[DEBUG] 다음 턴 app.invoke 완료", flush=True)
        print_turn_result(state)


if __name__ == "__main__":
    main()
