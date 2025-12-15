"""
Chroma DB 벡터 데이터베이스 서비스
"""
import os
from typing import List, Dict, Any
import logging
import requests
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Chroma DB 클라이언트 초기화"""
        self.persist_directory = persist_directory
        self.embedding_model = None
        self._client = None
        self._collection = None
        chroma_host = os.getenv("CHROMA_HOST")
        # 프로토콜 제거 (https:// 또는 http://)
        self.chroma_host = chroma_host.replace("https://", "").replace("http://", "") if chroma_host else None
        self.chroma_auth_token = os.getenv("CHROMA_AUTH_TOKEN")
    
    @property
    def client(self):
        """Lazy initialization for client"""
        if self._client is None:
            if self.chroma_host:
                logger.info(f"ChromaDB 서버 연결: {self.chroma_host}")
                try:
                    if self.chroma_auth_token:
                        self._client = chromadb.HttpClient(
                            host=self.chroma_host,
                            port=443,
                            ssl=True,
                            headers={"Authorization": f"Basic {self.chroma_auth_token}"}
                        )
                    else:
                        self._client = chromadb.HttpClient(
                            host=self.chroma_host,
                            port=443
                        )
                except Exception as e:
                    logger.warning(f"HttpClient 초기화 실패, 재시도: {e}")
                    # 인증 에러 무시하고 직접 API 호출
                    self._client = chromadb.HttpClient(
                        host=self.chroma_host,
                        port=443,
                        ssl=True,
                        headers={"Authorization": f"Basic {self.chroma_auth_token}"} if self.chroma_auth_token else {}
                    )
            else:
                logger.info(f"ChromaDB 로컬 모드: {self.persist_directory}")
                self._client = chromadb.PersistentClient(path=self.persist_directory)
        return self._client
    
    @property
    def collection(self):
        """Lazy initialization for collection"""
        if self._collection is None:
            try:
                self._collection = self.client.get_collection("news_embeddings")
                logger.info("기존 news_embeddings 컬렉션 로드")
            except Exception:
                self._collection = self.client.create_collection(
                    name="news_embeddings",
                    metadata={"hnsw:space": "cosine", "description": "Market Plan B 뉴스 임베딩"}
                )
                logger.info("news_embeddings 컬렉션 생성")
        return self._collection
    
    def add_news_embeddings(self, news_list: List[Dict[str, Any]]) -> int:
        """뉴스 임베딩 저장"""
        import time
        
        try:
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
        except Exception as e:
            logger.error(f"임베딩 저장 실패: {e}")
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
