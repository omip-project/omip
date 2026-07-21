@echo off
setlocal
cd /d "%~dp0.."
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "simulator\multi_sensor_simulator.py" %*
) else (
  echo Backend virtual environment was not found. Using the system Python.
  python "simulator\multi_sensor_simulator.py" %*
)
