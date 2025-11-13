#!/bin/bash

echo "뉴스 크롤링 스케줄러를 백그라운드에서 시작합니다..."

# 현재 스크립트의 실제 위치 기준으로 프로젝트 루트 찾기
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")/.."

cd "$PROJECT_ROOT" || exit 1

# nohup으로 백그라운드 실행 
PYTHONPATH="$PROJECT_ROOT" nohup python app/tasks/scheduler.py > app/tasks/scheduler.log 2>&1 &

# PID 저장
echo $! > app/tasks/scheduler.pid

echo "스케줄러가 백그라운드에서 실행 중입니다."
echo "PID: $(cat app/tasks/scheduler.pid)"
echo "로그 확인: tail -f app/tasks/scheduler.log"
echo "종료: kill \$(cat app/tasks/scheduler.pid)"