import jwt
from datetime import datetime, timedelta
from typing import Optional

SECRET_KEY = "market-plan-b-super-secret-key-2024-jwt-token-signing"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

class JWTService:
    @staticmethod
    def create_access_token(user_id: int, email: str) -> str:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        payload = {
            "user_id": user_id,
            "email": email,
            "exp": expire
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.JWTError:
            return None