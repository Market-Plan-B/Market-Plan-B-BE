# app/ai/tools/news_rag.py
# === 라이브러리 ===
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool
from app.services.chroma_service import chroma_service

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

from app.db.database import SessionLocal
from app.db.db_setting import Content   

from app.services.agent_service import (
    fetch_contents_by_titles,
    fetch_contents_for_news_rag,
)

# === CrudeBERT 설정 ===
CRUDEBERT_BASE_MODEL = "bert-base-uncased"
CRUDEBERT_MODEL_NAME = "Captain-1337/CrudeBERT"

_input_dim = 768
_target_dim = 64

np.random.seed(42)
_projection_matrix = np.random.randn(_input_dim, _target_dim)

_crude_tokenizer: Optional[AutoTokenizer] = None
_crude_model: Optional[AutoModel] = None
_device: Optional[str] = None


def _get_crudebert():
    """CrudeBERT 토크나이저/모델을 lazy 로드."""
    global _crude_tokenizer, _crude_model, _device

    if _crude_tokenizer is None or _crude_model is None or _device is None:
        tokenizer = AutoTokenizer.from_pretrained(CRUDEBERT_BASE_MODEL)
        model = AutoModel.from_pretrained(CRUDEBERT_MODEL_NAME)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        model.eval()

        _crude_tokenizer = tokenizer
        _crude_model = model
        _device = device

    return _crude_tokenizer, _crude_model, _device


def _crudebert_embedding(text: str) -> np.ndarray:
    """입력 텍스트를 CrudeBERT CLS 임베딩(768차원)으로 변환."""
    tokenizer, model, device = _get_crudebert()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512,
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    emb = outputs.last_hidden_state[:, 0, :].detach().cpu().numpy()[0]
    return emb


def _project_to_64(vec768: np.ndarray) -> np.ndarray:
    """768차원을 64차원으로 투영 (daily_news_data 와 동일 구조)."""
    return np.dot(vec768, _projection_matrix)


def _format_chroma_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ChromaDB / VDB query 결과를 간단한 리스트로 변환한다.
    - metadata: {"title": str}
    """
    ids = (raw.get("ids") or [[]])[0]
    dists = (raw.get("distances") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]

    results: List[Dict[str, Any]] = []
    for i in range(len(ids)):
        meta = metas[i] or {}
        results.append(
            {
                "id": ids[i],
                "distance": float(dists[i]),
                "title": meta.get("title"),
                "metadata": meta,
            }
        )
    return results


def _run_news_rag_core(
    query: str,
    collection: Any,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    semantic 모드: query 임베딩 → Chroma 유사도 검색
    """
    query_text = query or ""
    emb768 = _crudebert_embedding(query_text)
    query_vec = _project_to_64(emb768)

    raw = collection.query(
        query_embeddings=[query_vec.astype(float)],
        n_results=top_k,
    )
    return _format_chroma_results(raw)


def _merge_rag_with_db(
    rag_results: List[Dict[str, Any]],
    db_map: Dict[str, Content],
) -> List[Dict[str, Any]]:
    """
    semantic 모드: Chroma 결과 + DB contents merge
    """
    merged: List[Dict[str, Any]] = []

    for r in rag_results:
        title = r.get("title")
        content_row = db_map.get(title)

        if content_row is None:
            merged.append(
                {
                    "id": r.get("id"),
                    "distance": r.get("distance"),
                    "title": title,
                    "content": None,
                    "summary": None,
                    "published_at": None,
                    "source": None,
                    "source_score": None,
                    "url": None,
                    "metadata": r.get("metadata") or {},
                }
            )
        else:
            merged.append(
                {
                    "id": r.get("id"),
                    "distance": r.get("distance"),
                    "title": content_row.title,
                    "content": getattr(content_row, "content", None),
                    "summary": getattr(content_row, "summary", None),
                    "published_at": getattr(content_row, "published_at", None),
                    "source": getattr(content_row, "source", None),
                    "source_score": getattr(content_row, "source_score", None),
                    "url": getattr(content_row, "url", None),
                    "metadata": r.get("metadata") or {},
                }
            )

    return merged


def _format_sql_only_results(rows: List[Content]) -> List[Dict[str, Any]]:
    """
    SQL-only 모드 결과 포맷 (semantic 모드와 키를 맞춘다)
    """
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": f"content_{row.id}",
                "distance": None,
                "title": row.title,
                "content": getattr(row, "content", None),
                "summary": getattr(row, "summary", None),
                "published_at": getattr(row, "published_at", None),
                "source": getattr(row, "source", None),
                "source_score": getattr(row, "source_score", None),
                "url": getattr(row, "url", None),
                "metadata": {},
            }
        )
    return out


@tool("run_news_rag")
def run_news_rag(
    query: str = "",
    top_k: int = 5,
    cluster_id: Optional[Union[int, str]] = None,   # 인터페이스 유지용
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sort_by: Optional[str] = None,                  # "published_at" 또는 "source_score"
    sort_dir: str = "desc",                         # "asc" / "desc"
) -> List[Dict[str, Any]]:
    """
    뉴스 관련 통합 툴 (semantic + SQL-only)
    """
    is_semantic = bool(query and query.strip())
    collection = chroma_service.collection

    # === 1) semantic 모드: 내용/텍스트 기반 질문 ===
    if is_semantic:
        print("[DEBUG] run_news_rag: semantic mode")
        print("[DEBUG] collection count:", collection.count())
        print(f"[DEBUG] query: {query}")

        rag_results = _run_news_rag_core(
            query=query,
            collection=collection,
            top_k=top_k,
        )
        print(f"[DEBUG] Chroma 검색 결과: {len(rag_results)}개")

        titles = [r.get("title") for r in rag_results if r.get("title")]
        print(f"[DB_LOG] 추출된 titles: {len(titles)}개")
        if titles:
            print(f"[DB_LOG] 첫 번째 title: {titles[0]}")

        db = SessionLocal()
        try:
            print(f"[DB_LOG] DB 연결 성공, titles로 Content 조회 시작...")
            db_map = fetch_contents_by_titles(db, titles)
            print(f"[DB_LOG] DB 조회 완료: {len(db_map)}개 Content 조회됨")
            merged = _merge_rag_with_db(rag_results, db_map)
            print(f"[DB_LOG] 최종 merge 결과: {len(merged)}개")
        finally:
            db.close()
            print(f"[DB_LOG] DB 연결 종료")

        return merged

    # === 2) SQL-only 모드: published_at / source_score / 랭킹 질문 ===
    print("[DEBUG] run_news_rag: SQL-only mode")
    print(f"[DB_LOG] SQL-only 모드 파라미터: top_k={top_k}, start_date={start_date}, end_date={end_date}")
    print(f"[DB_LOG] sort_by={sort_by}, sort_dir={sort_dir}")

    db = SessionLocal()
    try:
        print(f"[DB_LOG] DB 연결 성공, SQL-only 쿼리 시작...")
        rows = fetch_contents_for_news_rag(
            db=db,
            top_k=top_k,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        print(f"[DB_LOG] SQL-only 쿼리 완료: {len(rows)}개 Content 조회됨")
        result = _format_sql_only_results(rows)
        print(f"[DB_LOG] 최종 포맷 결과: {len(result)}개")
    finally:
        db.close()
        print(f"[DB_LOG] DB 연결 종료")

    return result
