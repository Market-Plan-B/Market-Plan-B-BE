from fastapi import APIRouter
from datetime import date
from app.schemas.report import CardNewsResponse, ReportResponse

router = APIRouter(prefix="/api/reports", tags=["report"])

@router.get("/daily/cardnews", response_model=CardNewsResponse)
async def get_daily_cardnews():
    return CardNewsResponse(
        date=date.today(),
        title="일일 카드뉴스",
        summary="오늘의 주요 시장 동향 요약"
    )

@router.get("/daily/report", response_model=ReportResponse)
async def get_daily_report():
    return ReportResponse(
        date=date.today(),
        title="일일 리포트",
        content="오늘의 상세 시장 분석 내용"
    )

@router.get("/weekly/cardnews", response_model=CardNewsResponse)
async def get_weekly_cardnews():
    return CardNewsResponse(
        date=date.today(),
        title="주간 카드뉴스",
        summary="이번 주 주요 시장 동향 요약"
    )

@router.get("/weekly/report", response_model=ReportResponse)
async def get_weekly_report():
    return ReportResponse(
        date=date.today(),
        title="주간 리포트",
        content="이번 주 상세 시장 분석 내용"
    )