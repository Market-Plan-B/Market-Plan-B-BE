from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, report_router
from app.routers import dashboard_router
import uvicorn
from app.routers import report_router
from app.routers import analytics_router

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

app.include_router(auth.router)
app.include_router(report_router.router)
app.include_router(dashboard_router.router)
app.include_router(analytics_router.router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
