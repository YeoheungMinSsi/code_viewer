@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 가상환경(.venv)을 만들고 필요한 패키지를 설치합니다...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -m venv .venv
  ) else (
    python -m venv .venv
  )
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo 코드 산책을 시작합니다. 종료하려면 Ctrl+C를 누르세요.
.venv\Scripts\python.exe viewer.py
pause
