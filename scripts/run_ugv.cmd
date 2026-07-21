@echo off
call "%~dp0run_simulator.cmd" --vehicle-id OMIP-UGV-001 --vehicle-type GROUND_VEHICLE --vehicle-profile ugv-small-ackermann-v1 --duration 0 %*
