@echo off
call "%~dp0run_simulator.cmd" --vehicle-id OMIP-AUV-001 --vehicle-type AUV --vehicle-profile auv-research-thruster-v1 --duration 0 %*
