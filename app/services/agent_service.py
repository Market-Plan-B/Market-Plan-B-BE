from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.db.db_setting import ChatSession, ChatMessage, Content



# ----------------------------
# CHAT SESSION SAVE
# ----------------------------
def save_chat_session(
    db: Session,
    user_id: int,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[int] = None,
    end_session: bool = False,
) -> ChatSession:
    """
    chat_sessions 테이블 저장/업데이트

    - session_id 가 있으면: 해당 세션의 context / ended_at를 업데이트
    - session_id 가 없으면: 새 세션 생성
    """
    # 기존 세션 업데이트
    if session_id is not None:
        session = (
            db.query(ChatSession)
            .filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .first()
        )
        if not session:
            # 세션이 없으면 새로 생성
            session = ChatSession(
                user_id=user_id,
                context=context or {},
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

        # context 업데이트
        if context is not None:
            session.context = context

        # 세션 종료 플래그가 있으면 ended_at 세팅
        if end_session and session.ended_at is None:
            session.ended_at = datetime.utcnow()

        db.commit()
        db.refresh(session)
        return session

    # 새 세션 생성
    db_session = ChatSession(
        user_id=user_id,
        context=context or {},
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


# ----------------------------
# CHAT MESSAGE SAVE
# ----------------------------
def save_chat_message(
    db: Session,
    session_id: int,
    sender: str,
    message: str,
) -> ChatMessage:
    """
    chat_messages 테이블에 메세지 1건 저장
    """
    db_message = ChatMessage(
        session_id=session_id,
        sender=sender,
        message=message,
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


# ----------------------------
# CHAT LOAD (SESSION + MESSAGES)
# ----------------------------
def load_chat_session(
    db: Session,
    session_id: int,
) -> Optional[ChatSession]:
    """
    세션 1건 + 관련 메세지 관계까지 함께 로드
    (messages는 relationship으로 lazy 로딩 / 필요시 joinedload 사용)
    """
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id)
        .first()
    )
    return session


def load_chat_history(
    db: Session,
    session_id: int,
) -> List[ChatMessage]:
    """
    특정 session_id에 대한 전체 대화 히스토리 로드
    created_at 기준 오름차순 정렬
    """
    print(db.bind.url)
    
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    return messages


# ----------------------------
# (옵션) 유저의 최근 세션 로드
# ----------------------------
def load_last_session_by_user(
    db: Session,
    user_id: int,
) -> Optional[ChatSession]:
    """
    유저별로 가장 최근에 생성된 세션 1건 로드
    """
    session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.started_at.desc(), ChatSession.id.desc())
        .first()
    )
    return session




# ----------------------------
# NEWS_RAG용 CONTENT 조회: title 리스트 기반
# ----------------------------
def fetch_contents_by_titles(
    db: Session,
    titles: List[str],
) -> Dict[str, Content]:
    """
    title 리스트로 contents 테이블에서 뉴스 조회.
    - 반환: {title: Content 객체}
    """
    print(f"[DB_LOG] fetch_contents_by_titles - 요청된 titles 수: {len(titles)}")
    if titles:
        print(f"[DB_LOG] 첫 번째 title 예시: {titles[0][:50]}...")
    
    if not titles:
        print(f"[DB_LOG] titles가 비어있어서 빈 dict 반환")
        return {}

    print(f"[DB_LOG] DB 쿼리 실행 중... Content.title.in({len(titles)}개 titles)")
    rows = (
        db.query(Content)
        .filter(Content.title.in_(titles))
        .all()
    )
    print(f"[DB_LOG] DB 쿼리 결과: {len(rows)}개 Content 조회됨")
    
    result = {row.title: row for row in rows}
    print(f"[DB_LOG] 반환할 dict 크기: {len(result)}")
    return result


# ----------------------------
# NEWS_RAG용 CONTENT 조회: 날짜/점수 기반 랭킹
# ----------------------------
def fetch_contents_for_news_rag(
    db: Session,
    top_k: int,
    start_date: Optional[str],
    end_date: Optional[str],
    sort_by: Optional[str],
    sort_dir: str,
) -> List[Content]:
    """
    SQL-only 모드에서 사용하는 contents 조회 헬퍼.

    - start_date, end_date: "YYYY-MM-DD" 문자열 (없으면 필터 생략)
    - sort_by:
        - "published_at"  → 최신/과거 순 정렬
        - "source_score" → 점수 기준 정렬
        - None 또는 기타   → 기본값 "published_at"
    - sort_dir: "asc" 또는 "desc"
    """
    print(f"[DB_LOG] fetch_contents_for_news_rag 시작")
    print(f"[DB_LOG] 파라미터 - top_k: {top_k}, start_date: {start_date}, end_date: {end_date}")
    print(f"[DB_LOG] 파라미터 - sort_by: {sort_by}, sort_dir: {sort_dir}")
    
    q = db.query(Content)

    if start_date:
        print(f"[DB_LOG] 날짜 필터 추가: published_at >= {start_date}")
        q = q.filter(Content.published_at >= start_date)
    if end_date:
        print(f"[DB_LOG] 날짜 필터 추가: published_at <= {end_date}")
        q = q.filter(Content.published_at <= end_date)

    # 정렬 기준
    sort_by_normalized = (sort_by or "published_at").lower()
    if sort_by_normalized == "source_score":
        sort_col = Content.source_score
        print(f"[DB_LOG] 정렬 기준: source_score {sort_dir}")
    else:
        sort_col = Content.published_at
        print(f"[DB_LOG] 정렬 기준: published_at {sort_dir}")

    if sort_dir.lower() == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    if top_k:
        print(f"[DB_LOG] LIMIT 추가: {top_k}")
        q = q.limit(top_k)

    print(f"[DB_LOG] SQL 쿼리 실행 중...")
    results = q.all()
    print(f"[DB_LOG] SQL 쿼리 결과: {len(results)}개 Content 조회됨")
    
    if results:
        first_item = results[0]
        print(f"[DB_LOG] 첫 번째 결과 예시 - title: {first_item.title[:50]}..., published_at: {first_item.published_at}")
    
    return results