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
from app.db.db_setting import Region, Content, Analytics, RecommendedStrategy, ContentRegion
from datetime import datetime, date
from sqlalchemy import func
from sqlalchemy import Date
import json
import os
import httpx

EIA_API_KEY = os.getenv("EIA_API_KEY")
EIA_BASE = "https://api.eia.gov/v2"


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/map-impact", response_model=List[MapImpactResponse])
async def get_map_impact(db: Session = Depends(get_db)):
    """지도 정보 조회 - 전 세계 지도를 기반으로 각 국가의 영향도가 색상으로 시각화 (당일 업데이트된 데이터만)"""
    today = date.today()
    regions = db.query(Region).filter(
        Region.updated_at.cast(Date) == today
    ).all()
    return [
        MapImpactResponse(
            id=region.id,
            code=region.code,
            name=region.name,
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
        overall_score=float(analytics.overall_score) if analytics and analytics.overall_score else 0.0,
        overall_change=float(analytics.overall_change) if analytics and analytics.overall_change else 0.0
    )

@router.get("/region-impact", response_model=RegionImpactResponse)
async def get_region_impact(region_code: str = Query(..., description="국가 코드"), db: Session = Depends(get_db)):
    """국가별 뉴스 요약 정보 조회(최대 5개, 오늘 생성된 데이터만)"""
    region = db.query(Region).filter(Region.code == region_code).first()
    
    if not region:
        return RegionImpactResponse(
            region=RegionInfo(id=0, name="", code=region_code, region_score=0.0),
            contents=[]
        )

    # 매핑 테이블을 통해 컨텐츠 조회
    content_ids = db.query(ContentRegion.content_id).filter(
        ContentRegion.region_id == region.id
    ).all()
    content_ids = [cid[0] for cid in content_ids]
    
    if not content_ids:
        return RegionImpactResponse(
            region=RegionInfo(
                id=region.id,
                name=region.name,
                code=region.code,
                region_score=float(region.region_score) if region.region_score else 0.0
            ),
            contents=[]
        )
    
    contents = db.query(Content).filter(
        Content.id.in_(content_ids),
        Content.created_at.cast(Date) == date.today()
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
                published_date=content.published_at.strftime("%Y-%m-%d") if content.published_at else "",
                created_at=content.created_at.strftime("%Y-%m-%d %H:%M:%S") if content.created_at else ""
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
    """AI 기반 대응책 제안 정보 조회 (당일 생성된 데이터만)"""
    today = date.today()

    strategies = db.query(RecommendedStrategy).filter(
        RecommendedStrategy.created_at.cast(Date) == today
    ).all()
    
    return StrategiesResponse(
        strategies=[
            Strategy(
                id=strategy.id,
                name=strategy.name or "",
                horizon=strategy.horizon or "",
                objective=strategy.objective or "",
                preconditions=strategy.preconditions,
                actions=strategy.actions or [],
                data_evidence=strategy.data_evidence or {},
                risk_note=strategy.risk_note or "",
                created_at=strategy.created_at
            )
            for strategy in strategies
        ]
    )


# EIA API
US_CRUDE_SERIES = "WTTSTUS1"   # Weekly Total Stocks - United States


@router.get("/us-stocks")
async def get_us_crude_stocks():
    """
    미국 원유 재고 (EIA Weekly) 최신치 + 전주치 + 5년치(260주) 히스토리 제공
    """

    rows = await fetch_eia(
        f"{EIA_BASE}/petroleum/stoc/wstk/data/",
        {
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": US_CRUDE_SERIES,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": "260",  # 5년치
        }
    )

    # 데이터 없음
    if not rows:
        return {
            "latest": None,
            "prev": None,
            "period": None,
            "history": []
        }

    # 최신/전주 재고
    latest_row = rows[0]
    prev_row = rows[1] if len(rows) > 1 else None

    latest_value = float(latest_row["value"])
    prev_value = float(prev_row["value"]) if prev_row else None
    latest_period = latest_row["period"]

    # 히스토리(오래된 순으로)
    history = [
        {"period": r["period"], "value": float(r["value"])}
        for r in reversed(rows)
    ]

    return {
        "latest": latest_value,
        "prev": prev_value,
        "period": latest_period,
        "history": history
    }

OECD_TOTAL_SERIES = "WCSSTUS1"

PRODUCER_META = {
    "Saudi Arabia": {"code": "SAU", "iso": "SAU", "lat": 24, "lon": 45, "group": "OPEC+", "rank": 1},
    "Russia": {"code": "RUS", "iso": "RUS", "lat": 60, "lon": 90, "group": "OPEC+", "rank": 2},
    "United States": {"code": "USA", "iso": "USA", "lat": 38, "lon": -97, "group": "Non-OPEC", "rank": 3},
    "Iran": {"code": "IRN", "iso": "IRN", "lat": 32, "lon": 53, "group": "OPEC+", "rank": 4},
    "Iraq": {"code": "IRQ", "iso": "IRQ", "lat": 33, "lon": 44, "group": "OPEC+", "rank": 5},
    "UAE": {"code": "ARE", "iso": "ARE", "lat": 24, "lon": 54, "group": "OPEC+", "rank": 6},
}


def calc_avg(values):
    return sum(values) / len(values) if values else None


async def fetch_eia(url: str, params: dict) -> list:
    if not EIA_API_KEY:
        raise HTTPException(500, "EIA_API_KEY not configured")
    
    params["api_key"] = EIA_API_KEY
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(url, params=params)
    
    if res.status_code != 200:
        return []
    
    return res.json().get("response", {}).get("data", [])


@router.get("/oecd-inventory")
async def get_oecd_inventory():
    rows = await fetch_eia(
        f"{EIA_BASE}/petroleum/stoc/wstk/data/",
        {
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": OECD_TOTAL_SERIES,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": "260",
        }
    )

    if not rows:
        return {"regions": [], "globalStockDiffPct": None, "globalDaysDiff": None}

    latest = float(rows[0]["value"])
    values = [float(r["value"]) for r in rows]
    five_year_avg = calc_avg(values)
    
    daily_use = 45.0
    stocks_diff_pct = (latest - five_year_avg) / five_year_avg * 100 if five_year_avg else None
    days_of_supply = latest / daily_use
    days_of_supply_5yr = five_year_avg / daily_use if five_year_avg else None
    days_diff = days_of_supply - days_of_supply_5yr if days_of_supply_5yr else None

    return {
        "regions": [{
            "code": "OECD",
            "name": "OECD Total",
            "stocksMbbl": round(latest, 1),
            "stocksDiffPct": round(stocks_diff_pct, 1) if stocks_diff_pct else None,
            "daysOfSupply": round(days_of_supply, 1),
            "daysDiff": round(days_diff, 1) if days_diff else None
        }],
        "globalStockDiffPct": round(stocks_diff_pct, 1) if stocks_diff_pct else None,
        "globalDaysDiff": round(days_diff, 1) if days_diff else None
    }


@router.get("/supply-monitor")
async def get_supply_monitor():
    producers = []

    for name, meta in PRODUCER_META.items():
        rows = await fetch_eia(
            f"{EIA_BASE}/international/data/",
            {
                "frequency": "monthly",
                "data[0]": "value",
                "facets[countryRegionId][]": meta["iso"],
                "facets[productId][]": "55",
                "facets[activityId][]": "1",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": "24",
            }
        )

        if len(rows) < 13:
            continue

        try:
            latest = float(rows[0]["value"]) / 1000
            last_year = float(rows[12]["value"]) / 1000
            yoy = ((latest - last_year) / last_year * 100) if last_year else 0.0

            producers.append({
                "country": name,
                "code": meta["code"],
                "lat": meta["lat"],
                "lon": meta["lon"],
                "prodMbd": round(latest, 2),
                "yoyChangePct": round(yoy, 2),
                "group": meta["group"],
                "rank": meta["rank"]
            })
        except (KeyError, ValueError, IndexError):
            continue

    producers.sort(key=lambda x: x["rank"])
    
    opec = [p["yoyChangePct"] for p in producers if p["group"] == "OPEC+"]
    non_opec = [p["yoyChangePct"] for p in producers if p["group"] == "Non-OPEC"]

    return {
        "producers": producers,
        "opec_yoy_change": round(calc_avg(opec), 2) if opec else None,
        "non_opec_yoy_change": round(calc_avg(non_opec), 2) if non_opec else None,
    }