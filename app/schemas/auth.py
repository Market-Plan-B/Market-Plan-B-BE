from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    id: int
    name: str
    email: str
    access_token: str
    token_type: str = "bearer"