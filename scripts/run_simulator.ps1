$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."
$python = ".\backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
& $python ".\simulator\multi_sensor_simulator.py" @args
