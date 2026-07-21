@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt || exit /b 1
cd /d "%~dp0.."
set PYTHONPATH=%CD%\backend
python -m pytest -q
