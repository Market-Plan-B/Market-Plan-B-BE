from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from typing import List
from app.schemas.dashboard import (
    MapImpactResponse, 
    OverallImpactResponse, 
    RegionImpactResponse,
    FactorImpactResponse,
    StrategiesResponse,
    RegionInfo,
    NewsContent,
    Strategy
)
from app.db.database import get_db
from app.db.db_setting import Region, Content, Analytics, RecommendedStrategy
from datetime import datetime, date
from sqlalchemy import func

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/map-impact", response_model=List[MapImpactResponse])
async def get_map_impact(db: Session = Depends(get_db)):
    """지도 정보 조회 - 전 세계 지도를 기반으로 각 국가의 영향도가 색상으로 시각화"""
    regions = db.query(Region).all()
    return [
        MapImpactResponse(
            id=region.id,
            code=region.code,
            region_score=float(region.region_score) if region.region_score else 0.0
        )
        for region in regions
    ]

@router.get("/impact-overall", response_model=OverallImpactResponse)
async def get_impact_overall(db: Session = Depends(get_db)):
    """당일 전체 영향도 정보 조회"""
    today = date.today()
    analytics = db.query(Analytics).filter(Analytics.date == today).first()
    
    return OverallImpactResponse(
        date=today.strftime("%Y-%m-%d"),
        overall_score=float(analytics.overall_score) if analytics and analytics.overall_score else 0.0
    )

@router.get("/region-impact", response_model=RegionImpactResponse)
async def get_region_impact(region_code: str = Query(..., description="국가 코드"), db: Session = Depends(get_db)):
    """국가별 뉴스 요약 정보 조회(최대 5개)"""
    region = db.query(Region).filter(Region.code == region_code).first()
    
    if not region:
        return RegionImpactResponse(
            region=RegionInfo(id=0, name="", code=region_code, region_score=0.0),
            contents=[]
        )
    
    contents = db.query(Content).filter(
        Content.region_id == region.id
    ).order_by(Content.source_score.desc()).limit(5).all()
    
    return RegionImpactResponse(
        region=RegionInfo(
            id=region.id,
            name=region.name,
            code=region.code,
            region_score=float(region.region_score) if region.region_score else 0.0
        ),
        contents=[
            NewsContent(
                id=content.id,
                title=content.title,
                summary=content.summary or "",
                source_score=float(content.source_score) if content.source_score else 0.0,
                url=content.url or "",
                published_date=content.published_at.strftime("%Y-%m-%d") if content.published_at else ""
            )
            for content in contents
        ]
    )

@router.get("/factor-impact", response_model=FactorImpactResponse)
async def get_factor_impact(db: Session = Depends(get_db)):
    """요소별 영향도 정보 조회"""
    today = date.today()
    analytics = db.query(Analytics).filter(Analytics.date == today).first()
    
    return FactorImpactResponse(
        date=today.strftime("%Y-%m-%d"),
        variable_scores=analytics.variable_scores if analytics and analytics.variable_scores else {}
    )

@router.get("/strategies", response_model=StrategiesResponse)
async def get_strategies(db: Session = Depends(get_db)):
    """AI 기반 대응책 제안 정보 조회"""
    today = date.today()
    strategies = db.query(RecommendedStrategy).filter(
        RecommendedStrategy.date == today
    ).all()
    
    return StrategiesResponse(
        strategies=[
            Strategy(
                id=strategy.id,
                title=strategy.title,
                description=strategy.description
            )
            for strategy in strategies
        ]
    )