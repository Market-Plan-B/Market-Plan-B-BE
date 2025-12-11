# app/ai/test_main.py

from typing import Any
import os
import json
import joblib
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage   # 🔹 AIMessage 추가
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

# 🔹 DB 세션 & Chat CRUD import 추가
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.db_setting import DATABASE_URL
from app.services.agent_service import (
    save_chat_session,
    save_chat_message,
    load_chat_history,
)


# ---------------------------------------------------------------------
# 토글: True → 에이전트만 가볍게 테스트 (모델링/크롤 파이프라인 생략)
#       False → 전체 파이프라인 (데이터셋 + XAI + 예측까지 모두 수행)
# ---------------------------------------------------------------------
AGENT_TEST = True

# 🔹 CLI에서 사용할 기본 유저 ID (임시)
DEFAULT_USER_ID = 1

# 🔹 DB 세션 팩토리
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


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

def main(input_session_id: int | None = None) -> None:
    """브렌트 챗봇 CLI + LangGraph 트레이싱 진입점."""
    print("[DEBUG] test_main.main() 시작", flush=True)

    load_dotenv()

    # 1) LangGraph 트레이싱 / 체크포인터 session_id
    config_session_id = str(input_session_id) if input_session_id else "cli-brent-test"

    config = RunnableConfig(
        configurable={
            "session_id": config_session_id,
            "thread_id": config_session_id,
        },
        tags=["cli", "brent-agent"],
    )

    print("[DEBUG] LangGraph app 빌드 시작", flush=True)
    app = build_app()
    print("[DEBUG] LangGraph app 빌드 완료", flush=True)

    # DB 세션 오픈
    db: Session = SessionLocal()

    try:
        # ------------------------------------------------------------
        # 1) 뉴스 로드 + 전처리 + embedding
        #    - daily_news_list : 리스트 (모델 / DB 저장용)
        #    - daily_news_text : 문자열 (프롬프트 / planner용, 본문만)
        # ------------------------------------------------------------
        print("[DEBUG] raw_news 로드 시작", flush=True)
        raw_news = _db_load()

        print("[DEBUG] daily_news_list 생성 시작", flush=True)
        daily_news_list = _daily_news(raw_news)   # 리스트 반환
        print("[DEBUG] daily_news_list 생성 완료", flush=True)

        # ------------------------------------------------------------
        # 2) 모델링 파이프라인 실행 → model_result 생성
        #    🔹 DB용 raw(dict) + 프롬프트용 str 둘 다 만든다
        # ------------------------------------------------------------
        print("[DEBUG] 모델링 시작", flush=True)
        model_output = _daily_modeling(news_list=daily_news_list)
        raw_model_result = model_output                                    # DB 저장용 (dict)
        model_result_str = json.dumps(model_output, ensure_ascii=False)    # LLM 프롬프트용 문자열
        print("[DEBUG] 모델링 완료", flush=True)

        # ------------------------------------------------------------
        # 3) daily_report.html 로드 → daily_report 생성
        # ------------------------------------------------------------
        daily_report = _load_daily_report()

        # ------------------------------------------------------------
        # 4) 프롬프트용 문자열 생성 (planner에서 replace용)
        #    🔹 뉴스 리스트에서 content(본문)만 뽑아서 하나의 긴 문자열로 합치기
        # ------------------------------------------------------------
        contents: list[str] = []
        for article in daily_news_list:
            if isinstance(article, dict):
                # content가 있으면 우선 사용, 없으면 summary라도 사용
                text = article.get("content") or article.get("summary") or ""
            else:
                text = str(article)
            if text:
                contents.append(text)

        daily_news_text = "\n\n-----\n\n".join(contents)
        print(f"[DEBUG] daily_news_text length={len(daily_news_text)}", flush=True)

        # ------------------------------------------------------------
        # 5) ChatSession 생성 or 기존 세션 재사용
        #    - DB context에는 리스트/딕셔너리(raw) 그대로 저장
        # ------------------------------------------------------------
        if input_session_id is None:
            print("[DEBUG] 새로운 ChatSession 생성", flush=True)
            chat_session = save_chat_session(
                db=db,
                user_id=DEFAULT_USER_ID,
                context={
                    "daily_news": daily_news_list,     # DB에는 리스트(raw)
                    "model_result": raw_model_result,  # DB에는 dict(raw)
                    "daily_report": daily_report,
                },
            )
            session_id = chat_session.id
        else:
            print(f"[DEBUG] 기존 ChatSession 재사용: {input_session_id}", flush=True)
            session_id = input_session_id

        # ------------------------------------------------------------
        # 6) 최초 state 생성(first_start=True)
        #    - state.daily_news / state.model_result 는 문자열
        # ------------------------------------------------------------
        state: AgentState = initial_state(
            daily_news=daily_news_text,       # 🔹 본문만 이어붙인 문자열
            model_result=model_result_str,    # 🔹 JSON 문자열
            daily_report=daily_report,
            first_start=True,
        )
        print("[DEBUG] initial_state 생성 완료", flush=True)

        # 안내 출력
        print_intro()

        # ------------------------------------------------------------
        # 7) 첫 번째 app.invoke 실행
        # ------------------------------------------------------------
        print("[DEBUG] 첫 턴 invoke 실행(first_start=True)", flush=True)
        state = app.invoke(state, config=config)
        print_turn_result(state)

        # 첫 assistant 답변 저장
        final_answer = state.get("final_answer", "")
        if final_answer:
            save_chat_message(
                db=db,
                session_id=session_id,
                sender="assistant",
                message=final_answer,
            )

        # ------------------------------------------------------------
        # 8) 사용자 반복 입력 루프
        # ------------------------------------------------------------
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

            # 1) 유저 메시지 DB 저장
            save_chat_message(
                db=db,
                session_id=session_id,
                sender="user",
                message=user_input,
            )

            # 2) DB에서 전체 history 로드 → LangChain Message로 변환
            rows = load_chat_history(db, session_id=session_id)
            history_messages = []
            for row in rows:
                if row.sender == "user":
                    history_messages.append(HumanMessage(content=row.message))
                elif row.sender == "assistant":
                    history_messages.append(AIMessage(content=row.message))

            # 3) state 구성 (daily_news / model_result / daily_report는
            #    이미 LangGraph 내부 checkpointer / context에서 활용)
            invoke_state: AgentState = {
                "user_input": user_input,
                "first_start": False,
                "chat_history": history_messages,
            }

            print("[DEBUG] 다음 턴 invoke 실행(first_start=False)", flush=True)
            state = app.invoke(invoke_state, config=config)
            print_turn_result(state)

            # 4) assistant 답변 저장
            final_answer = state.get("final_answer", "")
            if final_answer:
                save_chat_message(
                    db=db,
                    session_id=session_id,
                    sender="assistant",
                    message=final_answer,
                )

    finally:
        db.close()
        print("[DEBUG] DB 세션 종료", flush=True)




if __name__ == "__main__":
    # python app/ai/test_main.py           → 새 세션
    # python app/ai/test_main.py 3         → session_id=3으로 이어서
    arg_session_id = None
    if len(sys.argv) >= 2:
        try:
            arg_session_id = int(sys.argv[1])
        except ValueError:
            print("[WARN] session_id 인자는 정수여야 합니다.", flush=True)

    main(input_session_id=arg_session_id)
