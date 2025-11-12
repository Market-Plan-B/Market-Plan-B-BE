#!/bin/bash

# 백그라운드에서 스케줄러 실행
echo "뉴스 크롤링 스케줄러를 백그라운드에서 시작합니다..."

# nohup으로 백그라운드 실행
nohup python scheduler.py > scheduler.log 2>&1 &

# PID 저장
echo $! > scheduler.pid

echo "스케줄러가 백그라운드에서 실행 중입니다."
echo "PID: $(cat scheduler.pid)"
echo "로그: tail -f scheduler.log"
echo "종료: kill $(cat scheduler.pid)"