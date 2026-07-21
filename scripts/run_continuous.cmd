@echo off
setlocal
cd /d "%~dp0.."
call "%~dp0run_all.cmd" --duration 0 %*
