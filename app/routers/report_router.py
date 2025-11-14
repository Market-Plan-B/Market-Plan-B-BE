from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func
from datetime import datetime
from app.schemas.report_schema import CardNewsResponse, ReportResponse, NewsItem, WeeklyRequest
from app.db.db_setting import DATABASE_URL, Content, Report
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports", tags=["report"])

engine = create_engine(DATABASE_URL)

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/daily/cardnews", response_model=CardNewsResponse)
async def get_daily_cardnews(query_date: str = Query(...), db: Session = Depends(get_db)):
    contents = db.query(Content).filter(
        func.date(Content.published_at) == query_date
    ).order_by(Content.source_score.desc()).limit(3).all()
    
    news = [NewsItem(
        date=query_date,
        title=c.title,
        summary=c.summary or "",
        url=c.url or ""
    ) for c in contents]
    
    return CardNewsResponse(news=news)

@router.get("/daily/report", response_model=ReportResponse)
async def get_daily_report(query_date: str = Query(...), db: Session = Depends(get_db)):
    report = db.query(Report).filter(
        Report.report_type == "daily",
        Report.start_date == query_date
    ).first()
    
    if report:
        return ReportResponse(
            start_date=report.start_date.strftime("%Y-%m-%d"),
            end_date=report.end_date.strftime("%Y-%m-%d"),
            html_resource=report.html_content
        )
    return ReportResponse(start_date=query_date, end_date=query_date, html_resource="")

@router.post("/weekly/cardnews", response_model=CardNewsResponse)
async def get_weekly_cardnews(request: WeeklyRequest, db: Session = Depends(get_db)):
    # end_date = request.end_date
    # start_date = request.start_date
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    contents = db.query(Content).filter(
        func.date(Content.published_at) >= start_date,
        func.date(Content.published_at) <= end_date
    ).order_by(Content.source_score.desc()).limit(3).all()
    
    news = [NewsItem(
        date=f"{start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}",
        title=c.title,
        summary=c.summary or "",
        url=c.url or ""
    ) for c in contents]
    
    return CardNewsResponse(news=news)


@router.post("/weekly/report", response_model=ReportResponse)
async def get_weekly_report(request: WeeklyRequest, db: Session = Depends(get_db)):
    report = db.query(Report).filter(
        Report.report_type == "weekly",
        Report.start_date == request.start_date,
        Report.end_date == request.end_date
    ).first()
    
    if report:
        return ReportResponse(
            start_date=report.start_date.strftime("%Y-%m-%d"),
            end_date=report.end_date.strftime("%Y-%m-%d"),
            html_resource=report.html_content
        )
    return ReportResponse(start_date=request.start_date, end_date=request.end_date, html_resource="")