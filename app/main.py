from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import report_router
from app.routers import dashboard_router
import uvicorn
from app.routers import analytics_router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Market Plan B API",
    description="Market Plan B 백엔드 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(report_router.router)
app.include_router(dashboard_router.router)
app.include_router(analytics_router.router)
app.include_router(admin.router)

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
