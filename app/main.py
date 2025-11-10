from fastapi import FastAPI
from app.routers import auth
import uvicorn
from app.routers import report

app = FastAPI(
    title="Market Plan B API",
    description="Market Plan B 백엔드 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


app.include_router(auth.router)
app.include_router(report.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
