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
        results = chroma_service.collection.get(
            limit=limit,
            include=["metadatas"]
        )
        
        return {
            "total": len(results["metadatas"]) if results["metadatas"] else 0,
            "news": [
                {
                    "cluster_id": meta.get("cluster_id", -1),
                    "published": meta.get("published", "N/A")
                }
                for meta in results["metadatas"]
            ] if results["metadatas"] else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/embeddings")
async def get_embeddings():
    """임베딩 벡터 값 조회"""
    try:
        results = chroma_service.collection.get(
            include=["metadatas", "embeddings"]
        )
        
        metadatas = results.get("metadatas", [])
        embeddings = results.get("embeddings", [])
        
        return {
            "total": len(metadatas),
            "news": [
                {
                    "cluster_id": meta.get("cluster_id"),
                    "published": meta.get("published"),
                    "summary_embedding": emb.tolist() if hasattr(emb, 'tolist') else emb
                }
                for meta, emb in zip(metadatas, embeddings)
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
