"""
Chroma DB 벡터 데이터베이스 서비스
"""
import os
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Chroma DB 클라이언트 초기화"""
        self.persist_directory = persist_directory
        self.embedding_model = None  # 지연 로딩 
        chroma_host = os.getenv("CHROMA_HOST")
        chroma_auth_token = os.getenv("CHROMA_AUTH_TOKEN")
        
        if chroma_host:
            # 서버 모드 (REST API)
            logger.info(f"ChromaDB 서버 연결: {chroma_host}")
            self.chroma_host = chroma_host
            self.chroma_auth_token = chroma_auth_token
            self.client = None
            self.collection = None
            self._init_collection_rest()
            )
            
            try:
                self.collection = self.client.get_collection("news_embeddings")
            except:
                self.collection = self.client.create_collection(
                    name="news_embeddings",
                    metadata={"hnsw:space": "cosine", "description": "Market Plan B 뉴스 임베딩"}
                )
        
        # 뉴스 컬렉션 생성/가져오기
        try:
            self.collection = self.client.get_collection("news_embeddings")
        except:
            self.collection = self.client.create_collection(
                name="news_embeddings",
                metadata={"hnsw:space": "cosine", "description": "Market Plan B 뉴스 임베딩 (CrudeBERT 64차원)"}
            )
        
        try:
            url = f"{self.chroma_host}/api/v2/collections"
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            collections = response.json()
            
            exists = any(c["name"] == "news_embeddings" for c in collections)
            
            if not exists:
                payload = {"name": "news_embeddings", "metadata": {"hnsw:space": "cosine"}}
                requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
                logger.info("news_embeddings 컬렉션 생성")
        except Exception as e:
            logger.error(f"컬렉션 초기화 실패: {e}")
    
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
            
            # === metadata에는 title만 저장 ===
            metadata = {
                "cluster_id": int(news.get("cluster_id", -1)),
                "title": news.get("title", "")
            }
            
            embeddings.append(embedding)
            metadatas.append({
                "cluster_id": int(news.get("cluster_id", -1)),
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
            if self.client:
                count = self.collection.count()
            else:
                headers = {"Authorization": f"Basic {self.chroma_auth_token}"}
                url = f"{self.chroma_host}/api/v2/collections/news_embeddings/count"
                response = requests.get(url, headers=headers, verify=False, timeout=10)
                count = response.json()
            
            return {"total_documents": count, "collection_name": "news_embeddings"}
        except Exception as e:
            logger.error(f"통계 조회 오류: {e}")
            return {"total_documents": 0, "collection_name": "unknown"}


# 전역 인스턴스
chroma_service = ChromaService()
