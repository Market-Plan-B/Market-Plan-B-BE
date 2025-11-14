from pydantic import BaseModel
from typing import List, Dict, Any

class ImpactResponse(BaseModel):
    date: str
    impact_score: str
    change_score: str
    features: Dict[str, List[float]]