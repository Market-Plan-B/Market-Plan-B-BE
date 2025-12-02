from pydantic import BaseModel
from typing import List, Optional

class CrawlingSourceBase(BaseModel):
    source_name: str
    base_url: str

class CrawlingSourceCreate(CrawlingSourceBase):
    pass

class CrawlingSourceUpdate(CrawlingSourceBase):
    pass

class CrawlingSourceResponse(CrawlingSourceBase):
    id: int
    is_active: bool
    categories: List = []
    
    class Config:
        from_attributes = True

class CrawlingSourceDetail(BaseModel):
    id: int
    source_name: str
    base_url: str
    
    class Config:
        from_attributes = True

class CrawlingSourcesListResponse(BaseModel):
    total: int
    active: int
    inactive: int
    sources: List[CrawlingSourceResponse]

class StatusUpdateRequest(BaseModel):
    is_active: bool

class StatusUpdateResponse(BaseModel):
    id: int
    is_active: bool

class CategoryResponse(BaseModel):
    id: int
    category: str
    is_active: bool
    
    class Config:
        from_attributes = True

class KeywordBulkUpdateRequest(BaseModel):
    category_ids: List[int]

class KeywordBulkUpdateResponse(BaseModel):
    updated: int
    categories_applied: List[int]