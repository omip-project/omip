@echo off
setlocal
cd /d "%~dp0.."
call scripts\run_simulator.cmd --vehicle-id OMIP-LOAD-001 --mission-id SYSTEM-LOAD-TEST-001 --scenario scenarios\high_message_rate.json --duration 30
