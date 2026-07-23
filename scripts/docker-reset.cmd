@echo off
setlocal
cd /d "%~dp0\.."

echo WARNING: This permanently deletes the OMIP Docker database, exports,
echo backups, runtime snapshots, and MQTT persistence data.
set /p CONFIRM=Type DELETE OMIP DATA to continue: 
if /I not "%CONFIRM%"=="DELETE OMIP DATA" (
  echo Reset cancelled.
  exit /b 1
)

docker compose down -v --remove-orphans
if errorlevel 1 exit /b %errorlevel%

echo OMIP Docker data has been deleted.
endlocal
