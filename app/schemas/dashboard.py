from pydantic import BaseModel
from typing import List, Dict
from datetime import date

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

class RegionImpactResponse(BaseModel):
    region: RegionInfo
    contents: List[NewsContent]

class FactorImpactResponse(BaseModel):
    date: str
    variable_scores: Dict[str, float]

class Strategy(BaseModel):
    id: int
    title: str
    description: str

class StrategiesResponse(BaseModel):
    strategies: List[Strategy]