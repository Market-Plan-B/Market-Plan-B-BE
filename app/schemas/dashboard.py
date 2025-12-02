from pydantic import BaseModel
from typing import List, Dict
from datetime import date, datetime

class MapImpactResponse(BaseModel):
    id: int
    code: str
    name: str
    region_score: float

class OverallImpactResponse(BaseModel):
    date: str
    overall_score: float

class RegionInfo(BaseModel):
    id: int
    name: str
    code: str
    region_score: float

class NewsContent(BaseModel):
    id: int
    title: str
    summary: str
    source_score: float
    url: str
    published_date: str
    created_at: str

class RegionImpactResponse(BaseModel):
    region: RegionInfo
    contents: List[NewsContent]

class FactorImpactResponse(BaseModel):
    date: str
    variable_scores: Dict[str, float]

class Strategy(BaseModel):
    id: int
    name: str
    horizon: str
    objective: str
    preconditions: str | None = None
    actions: List[str]            
    data_evidence: Dict[str, str] 
    risk_note: str | None = None
    created_at: datetime

class StrategiesResponse(BaseModel):
    strategies: List[Strategy]