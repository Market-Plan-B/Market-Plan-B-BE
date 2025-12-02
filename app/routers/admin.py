from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime, timezone, timedelta
from app.db.database import get_db
from app.models.crawling_source import CrawlingSource
from app.models.crawling_category import CrawlingCategory
from app.schemas.admin import (
    CrawlingSourcesListResponse, CrawlingSourceResponse, CrawlingSourceDetail,
    CrawlingSourceUpdate, StatusUpdateRequest, StatusUpdateResponse,
    CategoryResponse, KeywordBulkUpdateRequest, KeywordBulkUpdateResponse
)
from typing import List

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get("/sources", response_model=CrawlingSourcesListResponse)
async def get_crawling_sources(db: Session = Depends(get_db)):
    """크롤링 소스 목록 조회"""
    sources = db.query(CrawlingSource).all()
    
    total = len(sources)
    active = len([s for s in sources if s.is_active])
    inactive = total - active
    
    source_responses = []
    for source in sources:
        # JSON 컴럼에서 카테고리 ID 조회
        category_ids = source.category_ids or []
        categories = db.query(CrawlingCategory).filter(
            CrawlingCategory.id.in_(category_ids)
        ).all() if category_ids else []
        
        category_list = [{
            "id": cat.id,
            "category": cat.category,
            "isActive": cat.is_active
        } for cat in categories]
        
        source_responses.append(CrawlingSourceResponse(
            id=source.id,
            source_name=source.source_name,
            base_url=source.base_url,
            is_active=source.is_active,
            categories=category_list
        ))
    
    return CrawlingSourcesListResponse(
        total=total,
        active=active,
        inactive=inactive,
        sources=source_responses
    )

@router.get("/sources/{source_id}", response_model=CrawlingSourceDetail)
async def get_crawling_source_detail(source_id: int, db: Session = Depends(get_db)):
    """크롤링 소스 상세 조회"""
    source = db.query(CrawlingSource).filter(CrawlingSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")
    
    return CrawlingSourceDetail(
        id=source.id,
        source_name=source.source_name,
        base_url=source.base_url
    )

@router.put("/sources/keywords", response_model=KeywordBulkUpdateResponse)
async def bulk_update_keywords(
    keyword_update: KeywordBulkUpdateRequest,
    db: Session = Depends(get_db)
):
    """키워드 일괄 적용"""
    # 1. 모든 소스에 선택된 카테고리 적용
    sources = db.query(CrawlingSource).all()
    
    for source in sources:
        source.category_ids = keyword_update.category_ids
    
    # 2. 모든 카테고리를 비활성화
    db.query(CrawlingCategory).update({
        "is_active": False,
        "updated_at": datetime.now()
    })
    
    # 3. 선택된 카테고리만 활성화
    if keyword_update.category_ids:
        db.query(CrawlingCategory).filter(
            CrawlingCategory.id.in_(keyword_update.category_ids)
        ).update({
            "is_active": True,
            "updated_at": datetime.now()
        })
    
    db.commit()
    
    return KeywordBulkUpdateResponse(
        updated=len(sources),
        categories_applied=keyword_update.category_ids
    )

@router.put("/sources/{source_id}", response_model=CrawlingSourceDetail)
async def update_crawling_source(
    source_id: int, 
    source_update: CrawlingSourceUpdate, 
    db: Session = Depends(get_db)
):
    """크롤링 소스 수정"""
    source = db.query(CrawlingSource).filter(CrawlingSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")
    
    source.source_name = source_update.source_name
    source.base_url = source_update.base_url
    
    db.commit()
    db.refresh(source)
    
    return CrawlingSourceDetail(
        id=source.id,
        source_name=source.source_name,
        base_url=source.base_url
    )

@router.patch("/sources/{source_id}/status", response_model=StatusUpdateResponse)
async def update_source_status(
    source_id: int,
    status_update: StatusUpdateRequest,
    db: Session = Depends(get_db)
):
    """크롤링 소스 활성화/비활성화"""
    source = db.query(CrawlingSource).filter(CrawlingSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="소스를 찾을 수 없습니다")
    
    source.is_active = status_update.is_active
    db.commit()
    db.refresh(source)
    
    return StatusUpdateResponse(
        id=source.id,
        is_active=source.is_active
    )


@router.get("/keywords", response_model=List[CategoryResponse])
async def get_keywords(db: Session = Depends(get_db)):
    """전체 키워드 목록 조회"""
    categories = db.query(CrawlingCategory).all()
    
    return [CategoryResponse(
        id=category.id,
        category=category.category,
        is_active=category.is_active
    ) for category in categories]

