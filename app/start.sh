#!/bin/bash

python tasks/full_scheduler.py &

uvicorn main:app --host 0.0.0.0 --port 8000
