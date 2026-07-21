@echo off
setlocal
cd /d "%~dp0.."
start "OMIP v0.5.2 Backend" cmd /k call "%~dp0run_backend.cmd"
echo Waiting for the OMIP API...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; 1..120 | ForEach-Object { try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/health -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){exit 1}"
if errorlevel 1 (
  echo Backend did not become ready within 120 seconds.
  exit /b 1
)
start "OMIP v0.5.2 Multi-Sensor Simulator" cmd /k call "%~dp0run_simulator.cmd" %*
start "" http://127.0.0.1:8000
