from sqlalchemy.orm import Session
from app.db.db_setting import ChatSession, ChatMessage
from datetime import datetime
from typing import Optional, List, Dict, Any


class ChatService:
    
    @staticmethod
    def is_session_valid(session: ChatSession) -> bool:
        """세션 유효성 검사"""
        if not session:
            return False
        if session.ended_at:  # 수동 종료됨
            return False
        if session.expires_at and datetime.utcnow() > session.expires_at:
            return False
        return True
    
    @staticmethod
    def create_session(db: Session, user_id: int) -> ChatSession:
        """새 채팅 세션 생성 (24시간 만료)"""
        from datetime import datetime, timedelta
        
        expires_at = datetime.utcnow() + timedelta(hours=24)
        session = ChatSession(
            user_id=user_id,
            expires_at=expires_at
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    @staticmethod
    def end_session(db: Session, session_id: int) -> Optional[ChatSession]:
        """채팅 세션 종료"""
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.ended_at = datetime.now()
            db.commit()
            db.refresh(session)
        return session
    
    @staticmethod
    def add_message(db: Session, session_id: int, sender: str, message: str) -> ChatMessage:
        """메시지 추가 (sender: 'user' or 'ai')"""
        chat_message = ChatMessage(
            session_id=session_id,
            sender=sender,
            message=message
        )
        db.add(chat_message)
        db.commit()
        db.refresh(chat_message)
        return chat_message
    

    
    @staticmethod
    def get_session_history(db: Session, session_id: int) -> List[ChatMessage]:
        """세션의 채팅 히스토리 조회"""
        return db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).all()
    
    @staticmethod
    def get_user_sessions(db: Session, user_id: int) -> List[ChatSession]:
        """사용자의 모든 세션 조회"""
        return db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.started_at.desc()).all()