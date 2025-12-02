from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class CrawlingSource(Base):
    __tablename__ = "crawling_sources"
    
    id = Column(Integer, primary_key=True, index=True)
    base_url = Column(String(500), nullable=False)
    source_name = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    category_ids = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())