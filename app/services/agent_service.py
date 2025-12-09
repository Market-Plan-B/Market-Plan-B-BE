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


