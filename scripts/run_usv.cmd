@echo off
call "%~dp0run_simulator.cmd" --vehicle-id OMIP-USV-001 --vehicle-type USV --vehicle-profile usv-small-catamaran-v1 --duration 0 %*
