#!/bin/bash
set -e

export PYTHONPATH=/app

echo "Initializing database..."
python -c "from app.db.db_setting import init_db; init_db()" || echo "DB already initialized"

echo "Starting scheduler..."
python -m app.tasks.full_scheduler &
SCHEDULER_PID=$!

echo "Starting FastAPI server..."
cd /app
uvicorn app.main:app --host 0.0.0.0 --port 8000

wait $SCHEDULER_PID
