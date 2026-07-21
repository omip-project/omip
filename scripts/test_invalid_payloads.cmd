@echo off
setlocal
cd /d "%~dp0.."
python scripts\send_invalid_payloads.py --count 20
