from pydantic import BaseModel
from typing import List

class NewsItem(BaseModel):
    date: str
    title: str
    summary: str
    url: str

class CardNewsResponse(BaseModel):
    news: List[NewsItem]

class ReportResponse(BaseModel):
    start_date: str
    end_date: str
    html_resource: str

class WeeklyRequest(BaseModel):
    start_date: str
    end_date: str