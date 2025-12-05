from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func
from datetime import datetime
from app.schemas.report_schema import ReportResponse, WeeklyRequest, CardNewsImagesResponse
from app.db.db_setting import DATABASE_URL, Content, Report
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports", tags=["reports"])

engine = create_engine(DATABASE_URL)

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/daily/cardnews", response_model=CardNewsImagesResponse)
async def get_daily_cardnews(db: Session = Depends(get_db)):
    from datetime import date
    today = date.today()

    report = db.query(Report).filter(
        Report.report_type == "daily",
        Report.start_date == today
    ).first()

    if report and isinstance(report.images, list):
        return CardNewsImagesResponse(images=report.images)

    return CardNewsImagesResponse(images=[])

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