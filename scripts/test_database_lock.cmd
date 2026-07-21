@echo off
setlocal
cd /d "%~dp0.."
python scripts\test_database_lock.py --database backend\omip_v052.db --seconds 15
