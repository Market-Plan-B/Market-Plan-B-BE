from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Market Plan B API",
    description="Market Plan B 백엔드 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/")
async def root():
    return {"message": "Market Plan B API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)