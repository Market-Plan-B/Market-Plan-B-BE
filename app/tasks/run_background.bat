@echo off
echo 뉴스 크롤링 스케줄러를 백그라운드에서 시작합니다...

REM 현재 스크립트의 위치 기준으로 프로젝트 루트 찾기
set SCRIPT_DIR=%~dp0
for %%i in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fi
for %%i in ("%PROJECT_ROOT%..") do set PROJECT_ROOT=%%~fi

cd /d "%PROJECT_ROOT%" || (
    echo 프로젝트 루트 디렉토리로 이동 실패
    pause
    exit /b 1
)

REM PYTHONPATH 설정하고 백그라운드에서 실행
set PYTHONPATH=%PROJECT_ROOT%
start /b python app\tasks\scheduler.py > app\tasks\scheduler.log 2>&1

REM 프로세스 이름으로 확인
echo 스케줄러가 백그라운드에서 실행 중입니다.
echo 프로세스 확인: tasklist ^| findstr python
echo 로그 확인: type app\tasks\scheduler.log
echo 종료: taskkill /f /im python.exe

pause