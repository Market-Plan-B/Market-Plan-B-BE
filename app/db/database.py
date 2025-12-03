from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/market-plan-b"
DATABASE_URL = (
    "postgresql+psycopg2://postgres:Skala25a!23$"
    "@postgres-1-postgresql.postgres:5432/market-plan-b"
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()