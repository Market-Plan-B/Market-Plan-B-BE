"""
Chroma DB 조회 API
"""
from fastapi import APIRouter, Query, HTTPException
from app.services.chroma_service import chroma_service

router = APIRouter(prefix="/api/chroma", tags=["Chroma DB"])

@router.get("/stats")
async def get_stats():
    """Chroma DB 통계"""
    stats = chroma_service.get_collection_stats()
    return {
        "total_documents": stats["total_documents"],
        "collection_name": stats["collection_name"]
    }

@router.get("/list")
async def list_news(limit: int = Query(10, ge=1, le=100)):
    """저장된 뉴스 목록"""
    try:
        return chroma_service.get_news_list(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/embeddings")
async def get_embeddings():
    """임베딩 벡터 값 조회"""
    try:
        return chroma_service.get_embeddings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
