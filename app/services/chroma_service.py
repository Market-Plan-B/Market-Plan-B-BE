"""
Chroma DB 벡터 데이터베이스 서비스
"""
import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Any
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Chroma DB 클라이언트 초기화"""
        self.persist_directory = persist_directory
        
        # 임베딩 모델 로드
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Chroma DB 클라이언트 생성
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # 뉴스 컬렉션 생성/가져오기
        try:
            self.collection = self.client.get_collection("news_embeddings")
        except:
            self.collection = self.client.create_collection(
                name="news_embeddings",
                metadata={"hnsw:space": "cosine", "description": "Market Plan B 뉴스 임베딩 (384차원)"}
            )
        
        logger.info(f"Chroma DB 초기화 완료: {persist_directory}")
    
    def add_news_embeddings(self, news_list: List[Dict[str, Any]]) -> int:
        """뉴스 임베딩을 Chroma DB에 저장"""
        import time
        
        embeddings = []
        metadatas = []
        ids = []
        timestamp = int(time.time())
        
        for i, news in enumerate(news_list):
            doc_id = f"news_{timestamp}_{i}"
            
            embedding = news.get('summary_embedding')
            if not embedding:
                continue
            
            metadata = {
                "cluster_id": int(news.get("cluster_id", -1)),
                "published": str(news.get("published") or news.get("published_date", ""))
            }
            
            embeddings.append(embedding)
            metadatas.append(metadata)
            ids.append(doc_id)
        
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
        """컬렉션 통계 정보"""
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "collection_name": self.collection.name
            }
        except Exception as e:
            logger.error(f"Chroma DB 통계 조회 오류: {e}")
            return {"total_documents": 0, "collection_name": "unknown"}
    


# 전역 Chroma 서비스 인스턴스
chroma_service = ChromaService()