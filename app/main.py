from fastapi import FastAPI
from app.routers import auth

app = FastAPI(
    title="Market Plan B API",
    description="Market Plan B 백엔드 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(auth.router)
