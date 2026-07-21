@echo off
call "%~dp0run_simulator.cmd" --vehicle-id OMIP-UAV-001 --vehicle-type UAV --vehicle-profile uav-quadrotor-research-v1 --duration 0 %*
