from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from app.schemas.analytics_schema import ImpactResponse
from app.db.db_setting import DATABASE_URL, Analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

engine = create_engine(DATABASE_URL)

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/impact", response_model=ImpactResponse)
async def get_impact_info(query_date: str = Query(...), db: Session = Depends(get_db)):
    analytics = db.query(Analytics).filter(Analytics.date == query_date).first()
    
    if not analytics:
        raise HTTPException(status_code=404, detail="해당 날짜의 데이터를 찾을 수 없습니다")
    
    # 이전 날짜 데이터로 변화량 계산
    prev_analytics = db.query(Analytics).filter(Analytics.date < query_date).order_by(Analytics.date.desc()).first()
    change_score = "0.0"
    if prev_analytics and analytics.overall_score and prev_analytics.overall_score:
        change_score = str(round(float(analytics.overall_score) - float(prev_analytics.overall_score), 1))
    
    return ImpactResponse(
        date=query_date,
        impact_score=str(analytics.overall_score) if analytics.overall_score else "0.0",
        change_score=change_score,
        features=analytics.features if analytics.features else []
    )