# Getting started

This guide prepares a local OMIP development environment.

## Requirements

- Git
- Python 3.11 or later
- Windows PowerShell, Command Prompt, or a compatible shell
- Docker Desktop when using the bundled MQTT Broker

## Clone the repository

```powershell
git clone https://github.com/omip-project/omip.git
cd omip
```

## Start the backend

```powershell
.\scripts\run_backend.cmd
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`

## Start a simulation

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-UGV-001 `
  --vehicle-type GROUND_VEHICLE `
  --vehicle-profile ugv-small-ackermann-v1 `
  --scenario .\scenarios\ugv_active_avoidance.json `
  --duration 60
```

## Next

Continue with the [installation guide](installation.md) for environment details,
or review the [architecture](../architecture/index.md).
