from pydantic import BaseModel
from datetime import date

class CardNewsResponse(BaseModel):
    date: date
    title: str
    summary: str

class ReportResponse(BaseModel):
    date: date
    title: str
    content: str