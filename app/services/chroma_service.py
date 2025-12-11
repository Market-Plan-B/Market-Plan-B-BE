"""
Chroma DB 벡터 데이터베이스 서비스
"""
import os
from typing import List, Dict, Any
import logging
import requests
import chromadb

logger = logging.getLogger(__name__)

class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Chroma DB 클라이언트 초기화"""
        self.persist_directory = persist_directory
        self.embedding_model = None
        chroma_host = os.getenv("CHROMA_HOST")
        chroma_auth_token = os.getenv("CHROMA_AUTH_TOKEN")
        
        if chroma_host:
            # 서버 모드
            logger.info(f"ChromaDB 서버 연결: {chroma_host}")
            if chroma_auth_token:
                self.client = chromadb.HttpClient(
                    host=chroma_host,
                    headers={"Authorization": f"Bearer {chroma_auth_token}"}
                )
            else:
                self.client = chromadb.HttpClient(host=chroma_host)
        else:
            # 로컬 모드
            logger.info(f"ChromaDB 로컬 모드: {persist_directory}")
            self.client = chromadb.PersistentClient(path=persist_directory)
        
        # 컬렉션 초기화
        try:
            self.collection = self.client.get_collection("news_embeddings")
            logger.info("기존 news_embeddings 컬렉션 로드")
        except Exception:
            self.collection = self.client.create_collection(
                name="news_embeddings",
                metadata={"hnsw:space": "cosine", "description": "Market Plan B 뉴스 임베딩"}
            )
            logger.info("news_embeddings 컬렉션 생성")
    
    def add_news_embeddings(self, news_list: List[Dict[str, Any]]) -> int:
        """뉴스 임베딩 저장"""
        import time
        
        embeddings = []
        metadatas = []
        ids = []
        timestamp = int(time.time())
        
        for i, news in enumerate(news_list):
            embedding = news.get('summary_embedding')
            if not embedding:
                continue
            
            embeddings.append(embedding)
            metadatas.append({
                "cluster_id": int(news.get("cluster_id", -1)),
                "title": news.get("title", ""),
                "published": str(news.get("published", ""))
            })
            ids.append(f"news_{timestamp}_{i}")
        
        if embeddings:
            self.collection.add(
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Chroma DB에 {len(embeddings)}개 뉴스 임베딩 저장 완료")
            return len(embeddings)
        
        return 0
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        try:
            count = self.collection.count()
            return {"total_documents": count, "collection_name": "news_embeddings"}
        except Exception as e:
            logger.error(f"통계 조회 오류: {e}")
            return {"total_documents": 0, "collection_name": "news_embeddings"}


# 전역 인스턴스
chroma_service = ChromaService()
