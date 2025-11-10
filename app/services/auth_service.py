from sqlalchemy.orm import Session
from app.models.user import User
from app.services.jwt_service import JWTService

class AuthService:
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        user = db.query(User).filter(User.email == email, User.password == password).first()
        return user
    
    @staticmethod
    def create_access_token(user: User) -> str:
        return JWTService.create_access_token(user.id, user.email)