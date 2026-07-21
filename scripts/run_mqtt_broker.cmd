@echo off
setlocal
cd /d "%~dp0.."
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker was not found. Install Docker Desktop or start another MQTT broker on port 1883.
  exit /b 1
)
docker compose up -d mosquitto
if errorlevel 1 exit /b 1
echo.
echo Mosquitto is starting on 127.0.0.1:1883.
echo Open the OMIP dashboard and use MQTT ^> Enable.
powershell -NoProfile -Command "Start-Sleep -Seconds 2; Test-NetConnection 127.0.0.1 -Port 1883 | Select-Object ComputerName,RemotePort,TcpTestSucceeded"
