from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 잘못되었습니다")
    
    access_token = AuthService.create_access_token(user)
    
    return LoginResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        access_token=access_token
    )

@router.post("/logout")
async def logout():
    return {"message": "로그아웃되었습니다."}