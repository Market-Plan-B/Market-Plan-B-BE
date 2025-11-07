@echo off
echo ===============================
echo Market-Plan-B PostgreSQL + Python Setup 시작
echo ===============================

REM 1️⃣ Docker 컨테이너 실행
echo PostgreSQL Docker 컨테이너 실행 중...
docker run -d ^
    --name market-plan-b ^
    -e POSTGRES_USER=postgres ^
    -e POSTGRES_PASSWORD=postgres ^
    -e POSTGRES_DB=market-plan-b ^
    -p 5433:5432 ^
    ankane/pgvector:latest

@REM IF %ERRORLEVEL% NEQ 0 (
@REM     echo Docker 실행 실패. Docker Desktop이 켜져있는지 확인하세요.
@REM     exit /b 1
@REM )

REM 2️⃣ Python 가상환경 설정 (옵션)
echo Python 가상환경 생성 중...
python -m venv venv
call venv\Scripts\activate

REM 3️⃣ 의존성 설치
echo 필요한 패키지 설치 중...
pip install -r requirements.txt

REM 4️⃣ DB 초기화 Python 스크립트 실행
echo DB 초기화 스크립트 실행 중...
python ./app/db/db_setting.py

REM 5️⃣ 완료
echo 모든 설정이 완료되었습니다!
pause
