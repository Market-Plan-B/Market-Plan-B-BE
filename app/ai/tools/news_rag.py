# app/ai/tools/news_rag.py

# === 라이브러리 ===
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool
from app.services.chroma_service import chroma_service  # 공용 Chroma 서비스 사용

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

# === CrudeBERT + 64차원 프로젝션 설정 (summary_embedding과 동일 구조) ===

CRUDEBERT_BASE_MODEL = "bert-base-uncased"
CRUDEBERT_MODEL_NAME = "Captain-1337/CrudeBERT"

_input_dim = 768
_target_dim = 64

# daily_news_data 쪽과 동일하게 고정된 랜덤 프로젝션
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

    # CLS 토큰 임베딩: (1, 768) → (768,)
    emb = outputs.last_hidden_state[:, 0, :].detach().cpu().numpy()[0]
    return emb


def _project_to_64(vec768: np.ndarray) -> np.ndarray:
    """768차원을 64차원으로 투영 (daily_news_data 와 동일 구조)."""
    return np.dot(vec768, _projection_matrix)


# === 공통 함수 정의 ===
def _format_chroma_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    ChromaDB / VDB query 결과를 간단한 리스트로 변환한다.

    VDB 문서 구조 가정:
    - metadata:
        - "cluster_id": int (예: 2)
        - "published": str (예: "2025-11-30")
        - "summary": str (뉴스 요약)
        - "title": str (선택)
        - "url": str (선택)
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
                "summary": meta.get("summary"),
                "title": meta.get("title"),
                "url": meta.get("url"),
                "cluster_id": meta.get("cluster_id"),
                "published": meta.get("published"),
                "metadata": meta,
            }
        )
    return results


def _build_where_filter(
    cluster_id: Optional[Union[int, str]],
    start_date: Optional[str],
    end_date: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    VDB용 where 필터를 구성한다.

    - cluster_id: 특정 클러스터만 조회하고 싶을 때 (int 또는 str)
    - start_date, end_date: "YYYY-MM-DD" 형태 문자열 가정
    """
    where: Dict[str, Any] = {}

    if cluster_id is not None:
        if isinstance(cluster_id, str) and cluster_id.isdigit():
            where["cluster_id"] = int(cluster_id)
        else:
            where["cluster_id"] = cluster_id

    date_filter: Dict[str, Any] = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date
    if date_filter:
        where["published"] = date_filter

    if not where:
        return None
    return where


def _run_news_rag_core(
    query: str,
    collection: Any,
    top_k: int = 5,
    cluster_id: Optional[Union[int, str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    실제 Chroma 컬렉션에 쿼리 날리는 코어 함수.
    - 컬렉션에는 CrudeBERT+프로젝션으로 만든 summary_embedding이 저장되어 있음
    """
    where = _build_where_filter(
        cluster_id=cluster_id,
        start_date=start_date,
        end_date=end_date,
    )

    # query 가 빈 문자열이어도, 기간/클러스터 필터 기반 대표 뉴스 검색용으로 허용
    query_text = query or ""

    # 1) CrudeBERT CLS(768차원)
    emb768 = _crudebert_embedding(query_text)
    # 2) 64차원으로 투영 (저장된 summary_embedding과 동일 차원/구조)
    query_vec = _project_to_64(emb768)

    raw = collection.query(
        query_embeddings=[query_vec.astype(float)],
        n_results=top_k,
        where=where,
    )
    return _format_chroma_results(raw)


# === LangChain Tool 래퍼 ===
@tool("run_news_rag")
def run_news_rag(
    query: str,
    top_k: int = 5,
    cluster_id: Optional[Union[int, str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    비슷한 내용을 가진 뉴스를 VDB(ChromaDB)에서 검색하고,
    메타데이터에 저장된 summary/title/url 등을 그대로 반환하는 툴.

    파라미터:
    - query: 유저 질문/문장 (요약 텍스트 기준 검색)
    - top_k: 가져올 뉴스 개수 (기본 5개)
    - cluster_id: 특정 클러스터만 보고 싶을 때 (예: 2 또는 "2")
    - start_date / end_date: "YYYY-MM-DD" 형식의 날짜 필터

    반환:
    - [
        {
          "id": str,              # Chroma 내부 문서 id
          "distance": float,      # 벡터 유사도 거리
          "summary": str | None,  # 뉴스 요약 (metadata.summary)
          "title": str | None,    # 선택
          "url": str | None,      # 선택
          "cluster_id": ...,
          "published": ...,
          "metadata": {...},
        },
        ...
      ]
    """
    collection = chroma_service.collection
    print("[DEBUG] collection count:", collection.count())

    # 1) Chroma RAG 검색 (PostgreSQL 연동 없이 바로 사용)
    rag_results = _run_news_rag_core(
        query=query,
        collection=collection,
        top_k=top_k,
        cluster_id=cluster_id,
        start_date=start_date,
        end_date=end_date,
    )

    return rag_results
