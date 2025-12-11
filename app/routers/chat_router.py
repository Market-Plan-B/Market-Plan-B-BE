from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from app.db.database import get_db
from app.services.chat_service import ChatService
from app.ai.graph import build_app, run_chat_round
from app.ai.state import AgentState
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Pydantic 모델들
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    user_id: int

class ChatResponse(BaseModel):
    session_id: int
    message: str
    suggestions: List[str]

class SessionResponse(BaseModel):
    id: int
    started_at: str
    ended_at: Optional[str]

class MessageResponse(BaseModel):
    id: int
    sender: str
    message: str
    created_at: str

# 전역 앱 인스턴스
chat_app = build_app()

# CrudeBERT 모델 워밍업
def warmup_models():
    """첫 번째 요청 시 모델 로딩 지연을 방지하기 위한 워밍업"""
    try:
        print("[LOG] CrudeBERT 모델 워밍업 시작...")
        from app.ai.tools.news_rag import _get_crudebert, _crudebert_embedding
        # 모델 로드
        _get_crudebert()
        # 테스트 임베딩
        _crudebert_embedding("테스트")
        print("[LOG] CrudeBERT 모델 워밍업 완료")
    except Exception as e:
        print(f"[LOG] CrudeBERT 모델 워밍업 실패: {e}")

# 서버 시작 시 워밍업 실행
warmup_models()

@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest, db: Session = Depends(get_db)):
    """채팅 메시지 전송"""
    try:
        # 테스트용 사용자 생성 (없으면)
        from app.db.db_setting import User
        test_user = db.query(User).filter(User.id == request.user_id).first()
        if not test_user:
            test_user = User(
                id=request.user_id,
                name=f"테스트사용자{request.user_id}",
                email=f"test{request.user_id}@example.com",
                password="test123",
                role="user"
            )
            db.add(test_user)
            db.commit()
            print(f"[LOG] 테스트 사용자 생성: {test_user.id}")
        
        print(f"[LOG] 요청 받음: user_id={request.user_id}, session_id={request.session_id}, message={request.message}")
        
        # 세션 처리
        if request.session_id:
            print(f"[LOG] 기존 세션 조회: {request.session_id}")
            from app.db.db_setting import ChatSession
            
            session = db.query(ChatSession).filter(
                ChatSession.id == request.session_id
            ).first()
            
            print(f"[SESSION_DEBUG] 조회된 세션: {session.id if session else 'None'}")
            if session:
                print(f"[SESSION_DEBUG] 세션 정보: user_id={session.user_id}, started_at={session.started_at}, expires_at={session.expires_at}")
            
            if not ChatService.is_session_valid(session):
                print(f"[LOG] 세션 만료 또는 없음, 새 세션 생성")
                session = ChatService.create_session(db, request.user_id)
                print(f"[SESSION_DEBUG] 새로 생성된 세션: {session.id}")
            else:
                print(f"[LOG] 세션 찾음: {session.id}")
        else:
            # 새 세션 생성
            print(f"[LOG] 새 세션 생성 중...")
            session = ChatService.create_session(db, request.user_id)
            print(f"[LOG] 새 세션 생성됨: {session.id} (만료: {session.expires_at})")
            print(f"[SESSION_DEBUG] 새 세션 상세: user_id={session.user_id}, started_at={session.started_at}")
        
        # 사용자 메시지 저장
        print(f"[LOG] 사용자 메시지 저장 중...")
        print(f"[MESSAGE_DEBUG] 저장할 메시지: session_id={session.id}, sender=user, message_len={len(request.message)}")
        
        user_message = ChatService.add_message(
            db, session.id, "user", request.message
        )
        
        print(f"[LOG] 사용자 메시지 저장됨: {user_message.id}")
        print(f"[MESSAGE_DEBUG] 저장된 메시지 정보: id={user_message.id}, created_at={user_message.created_at}")
        
        # AI 응답 생성
        print(f"[LOG] AI 응답 생성 시작...")
        
        # 기존 채팅 히스토리 로드
        print(f"[LOG] 채팅 히스토리 로드 중...")
        print(f"[HISTORY_DEBUG] 세션 ID: {session.id}")
        
        chat_history = []
        messages = ChatService.get_session_history(db, session.id)
        
        print(f"[HISTORY_DEBUG] DB에서 조회된 전체 메시지 수: {len(messages)}")
        for i, msg in enumerate(messages):
            print(f"[HISTORY_DEBUG] 메시지 {i+1}: sender={msg.sender}, created_at={msg.created_at}, message_len={len(msg.message)}")
        
        # 방금 추가한 메시지는 제외하되, 이전 대화들은 모두 포함
        if len(messages) > 1:
            # 마지막 메시지(방금 추가한 user 메시지) 제외
            history_messages = messages[:-1]
            print(f"[HISTORY_DEBUG] 히스토리용 메시지 수 (마지막 제외): {len(history_messages)}")
            
            for msg in history_messages:
                if msg.sender == "user":
                    chat_history.append(HumanMessage(content=msg.message))
                    print(f"[HISTORY_DEBUG] User 메시지 추가: {msg.message[:50]}...")
                elif msg.sender == "ai":
                    chat_history.append(AIMessage(content=msg.message))
                    print(f"[HISTORY_DEBUG] AI 메시지 추가: {msg.message[:50]}...")
        else:
            print(f"[HISTORY_DEBUG] 첫 번째 메시지이므로 히스토리 없음")
        
        print(f"[LOG] 히스토리 로드 완료: {len(chat_history)}개 메시지")
        print(f"[HISTORY_DEBUG] 최종 chat_history 타입들: {[type(msg).__name__ for msg in chat_history]}")
        if chat_history:
            print(f"[HISTORY_DEBUG] 첫 번째 히스토리 메시지: {chat_history[0].content[:50]}...")
        
        # LangGraph가 모든 데이터 조회를 처리함
        
        # AI 상태 구성
        print(f"[LOG] AI 상태 구성 중...")
        print(f"[STATE_DEBUG] chat_history 길이: {len(chat_history)}")
        print(f"[STATE_DEBUG] first_start 값: {len(chat_history) == 0}")
        
        initial_state = AgentState(
            user_input=request.message,
            chat_history=chat_history,
            first_start=len(chat_history) == 0
        )
        
        print(f"[STATE_DEBUG] State 생성 후 chat_history: {len(initial_state.get('chat_history', []))}개")
        
        # AI 실행
        print(f"[LOG] AI 실행 중...")
        print(f"[STATE_DEBUG] 초기 상태: user_input={initial_state.get('user_input', '')[:50]}..., first_start={initial_state.get('first_start')}, chat_history_len={len(initial_state.get('chat_history', []))}")
        
        result = chat_app.invoke(initial_state)
        
        print(f"[LOG] AI 실행 완료")
        print(f"[STATE_DEBUG] 최종 상태 키들: {list(result.keys())}")
        print(f"[STATE_DEBUG] goal: {result.get('goal', 'None')}")
        print(f"[STATE_DEBUG] final_answer 길이: {len(result.get('final_answer', ''))}")
        print(f"[STATE_DEBUG] recommend_query 길이: {len(result.get('recommend_query', ''))}")
        print(f"[STATE_DEBUG] tool_results 키들: {list(result.get('tool_results', {}).keys())}")
        
        # 결과에서 응답과 추천 질문 추출
        ai_response = result.get("final_answer", "죄송합니다. 응답을 생성할 수 없습니다.")
        recommend_query = result.get("recommend_query", "")
        
        # 추천 질문 파싱
        suggestions = []
        if recommend_query and recommend_query.strip():
            try:
                import json
                # 마크다운 코드 블록 제거
                clean_query = recommend_query.strip()
                if clean_query.startswith("```json"):
                    clean_query = clean_query[7:]  # ```json 제거
                if clean_query.endswith("```"):
                    clean_query = clean_query[:-3]  # ``` 제거
                clean_query = clean_query.strip()
                
                suggestions_data = json.loads(clean_query)
                questions = suggestions_data.get("questions", [])
                suggestions = [q.get("text", "") for q in questions if q.get("text")]
            except Exception as parse_error:
                print(f"[LOG] 추천 질문 파싱 실패: {parse_error}")
                print(f"[LOG] 원본 응답: {recommend_query[:200]}...")
                suggestions = []
        
        print(f"[LOG] AI 응답: {ai_response[:50] if ai_response else 'None'}...")
        print(f"[LOG] 제안 질문: {suggestions}")
        
        # AI 응답 저장
        print(f"[LOG] AI 응답 저장 중...")
        print(f"[MESSAGE_DEBUG] 저장할 AI 응답: session_id={session.id}, sender=ai, response_len={len(ai_response)}")
        
        ai_message = ChatService.add_message(
            db, session.id, "ai", ai_response
        )
        
        print(f"[LOG] AI 응답 저장됨: {ai_message.id}")
        print(f"[MESSAGE_DEBUG] 저장된 AI 메시지 정보: id={ai_message.id}, created_at={ai_message.created_at}")
        
        # 세션 활동 시간 업데이트
        from datetime import datetime
        session.last_activity_at = datetime.utcnow()
        db.commit()
        
        # 제안 질문은 응답에만 포함 (DB 저장 안함)
        if suggestions:
            print(f"[LOG] 제안 질문 {len(suggestions)}개 생성됨")
        
        print(f"[LOG] 요청 처리 완료")
        return ChatResponse(
            session_id=session.id,
            message=ai_response,
            suggestions=suggestions
        )
        
    except Exception as e:
        import traceback
        print(f"Error in send_message: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("/session", response_model=SessionResponse)
async def create_session(user_id: int, db: Session = Depends(get_db)):
    """새 채팅 세션 생성"""
    # 테스트용 사용자 생성 (없으면)
    from app.db.db_setting import User
    test_user = db.query(User).filter(User.id == user_id).first()
    if not test_user:
        test_user = User(
            id=user_id,
            name=f"테스트사용자{user_id}",
            email=f"test{user_id}@example.com",
            password="test123",
            role="user"
        )
        db.add(test_user)
        db.commit()
    
    session = ChatService.create_session(db, user_id)
    return SessionResponse(
        id=session.id,
        started_at=session.started_at.isoformat(),
        ended_at=session.ended_at.isoformat() if session.ended_at else None
    )

@router.delete("/session/{session_id}")
async def end_session(session_id: int, db: Session = Depends(get_db)):
    """채팅 세션 종료"""
    session = ChatService.end_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session ended successfully"}

@router.get("/sessions/{user_id}", response_model=List[SessionResponse])
async def get_user_sessions(user_id: int, db: Session = Depends(get_db)):
    """사용자의 모든 세션 조회"""
    sessions = ChatService.get_user_sessions(db, user_id)
    return [
        SessionResponse(
            id=session.id,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            context=session.context
        )
        for session in sessions
    ]

@router.get("/history/{session_id}", response_model=List[MessageResponse])
async def get_session_history(session_id: int, db: Session = Depends(get_db)):
    """세션의 채팅 히스토리 조회"""
    messages = ChatService.get_session_history(db, session_id)
    return [
        MessageResponse(
            id=msg.id,
            sender=msg.sender,
            message=msg.message,
            created_at=msg.created_at.isoformat()
        )
        for msg in messages
    ]

@router.get("/debug/state")
async def debug_state(message: str = "테스트 메시지"):
    """디버깅용 State 조회"""
    try:
        initial_state = AgentState(
            user_input=message,
            chat_history=[],
            first_start=True
        )
        
        # 실행 전 상태
        print(f"[DEBUG] 실행 전 State: {dict(initial_state)}")
        
        result = chat_app.invoke(initial_state)
        
        # 실행 후 상태
        return {
            "initial_state": dict(initial_state),
            "final_state": dict(result),
            "state_keys": list(result.keys()),
            "goal": result.get("goal"),
            "tool_results_keys": list(result.get("tool_results", {}).keys())
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/suggestions")
async def get_initial_suggestions(session_id: int, db: Session = Depends(get_db)):
    """초기 추천 질문 조회 (대화 시작 전)"""
    try:
        print(f"[LOG] 초기 추천 질문 요청 시작...")
        
        # LangGraph가 모든 데이터 조회를 처리함
        
        # 초기 추천 질문용 상태
        initial_state = AgentState(
            user_input="",
            chat_history=[],
            first_start=True
        )
        
        print(f"[LOG] AI 실행 시작 (interinferencer -> questiongenerator)...")
        print(f"[STATE_DEBUG] 초기 추천 질문 상태: first_start={initial_state.get('first_start')}")
        
        # AI 실행: interinferencer -> questiongenerator 경로
        result = chat_app.invoke(initial_state)
        
        print(f"[LOG] AI 실행 완료")
        
        # 추천 질문 추출 및 파싱
        recommend_query = result.get("recommend_query", "")
        print(f"[LOG] recommend_query: {recommend_query[:200] if recommend_query else 'None'}...")
        
        suggestion_texts = []
        if recommend_query and recommend_query.strip():
            try:
                import json
                # 마크다운 코드 블록 제거
                clean_query = recommend_query.strip()
                if clean_query.startswith("```json"):
                    clean_query = clean_query[7:]  # ```json 제거
                if clean_query.endswith("```"):
                    clean_query = clean_query[:-3]  # ``` 제거
                clean_query = clean_query.strip()
                
                suggestions_data = json.loads(clean_query)
                questions = suggestions_data.get("questions", [])
                suggestion_texts = [q.get("text", "") for q in questions if q.get("text")]
                print(f"[LOG] 파싱 성공: {len(suggestion_texts)}개 질문")
            except Exception as parse_error:
                print(f"[LOG] JSON 파싱 실패: {parse_error}")
                print(f"[LOG] 원본 응답: {recommend_query[:200]}...")
                suggestion_texts = []
        
        # 초기 추천 질문은 DB에 저장하지 않음 (시스템 메시지이므로)
        # 단순히 추천 질문만 반환
        print(f"[LOG] 초기 추천 질문 생성 완료 (DB 저장 안함)")
        
        print(f"[LOG] 최종 반환: {suggestion_texts}")
        
        return {
            "suggestions": suggestion_texts
        }
        
    except Exception as e:
        import traceback
        print(f"[LOG] 초기 추천 질문 에러: {str(e)}")
        print(f"[LOG] Traceback: {traceback.format_exc()}")
        return {
            "suggestions": []
        }