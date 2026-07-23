@echo off
setlocal
cd /d "%~dp0\.."

echo Starting OMIP and the optional demo simulator...
docker compose --profile demo up -d --build
if errorlevel 1 exit /b %errorlevel%

echo.
echo Dashboard: http://127.0.0.1:8000
endlocal
