@echo off
chcp 65001 >nul
echo 뉴스 크롤링 스케줄러를 백그라운드에서 시작합니다...

REM 현재 스크립트의 디렉토리 (예: ...\Market-Plan-B-BE\app\tasks\)
set SCRIPT_DIR=%~dp0

REM 프로젝트 루트 (...\Market-Plan-B-BE)
for %%i in ("%SCRIPT_DIR%..\..") do set PROJECT_ROOT=%%~fi

cd /d "%PROJECT_ROOT%" || (
    echo ❌ 프로젝트 루트 디렉토리로 이동 실패: %PROJECT_ROOT%
    pause
    exit /b 1
)

REM PYTHONPATH 설정하고 백그라운드에서 실행
set PYTHONPATH=%PROJECT_ROOT%
echo 🔄 실행 경로: %PROJECT_ROOT%
start /b python app\tasks\scheduler.py > app\tasks\scheduler.log 2>&1

REM 실행 결과 안내
echo ---------------------------------------
echo 스케줄러가 백그라운드에서 실행 중입니다.
echo 프로세스 확인 : tasklist ^| findstr python
echo 로그 확인     : type app\tasks\scheduler.log
echo 종료 명령     : taskkill /f /im python.exe
echo ---------------------------------------

pause
