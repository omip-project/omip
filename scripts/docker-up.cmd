@echo off
setlocal
cd /d "%~dp0\.."

if not exist .env (
  copy /Y .env.example .env >nul
  echo Created .env from .env.example
)

echo Building and starting OMIP...
docker compose up -d --build
if errorlevel 1 exit /b %errorlevel%

echo.
echo OMIP is starting.
echo Dashboard: http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Run scripts\docker-status.cmd to check service health.
endlocal
