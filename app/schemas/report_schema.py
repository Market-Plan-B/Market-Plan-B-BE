from pydantic import BaseModel
from typing import List



class CardNewsImagesResponse(BaseModel):
    images: List[str]

class ReportResponse(BaseModel):
    start_date: str
    end_date: str
    html_resource: str

class WeeklyRequest(BaseModel):
    start_date: str
    end_date: str