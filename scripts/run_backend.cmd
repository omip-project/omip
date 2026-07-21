@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv .venv || exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt || exit /b 1
python -m uvicorn app.main:app --reload
