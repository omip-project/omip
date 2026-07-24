## Foundation v1.0.1 Patch

This patch changes the default Docker host port from `8000` to `18080` to
improve compatibility with Windows, WSL and Hyper-V reserved port ranges.

### Fixed

- Default Docker host port changed to `18080`
- Quick Start updated
- Troubleshooting guidance updated

# RELEASE_NOTES_v1.0.md

# OMIP Foundation v1.0 Release Notes

Release: Foundation v1.0

## Overview

This is the first public foundation release of OMIP.

The goal of this release is to provide a stable local development
environment that can be deployed in minutes and serve as the basis
for future platform development.

## Highlights

### Platform

- Initial project structure
- Docker-based runtime
- Backend service
- MQTT broker integration
- Web dashboard

### Simulation

- Demo vehicle simulator
- Mission creation
- Sensor registration
- Heartbeat publishing
- Raw sensor streaming

### Infrastructure

- Docker Compose deployment
- Environment configuration
- Health endpoints
- MQTT compatibility improvements
- Windows deployment support

### Documentation

- README improvements
- Quick Start Guide
- Installation Guide
- Troubleshooting Guide
- FAQ
- First Mission tutorial

## Known Limitations

- Local SQLite intended for development
- Demo simulator only
- Authentication is minimal
- No HA deployment yet
- SDKs are planned but not included

## Upgrade Notes

If upgrading from early Foundation snapshots:

- Replace .env with the latest .env.example values.
- Rebuild Docker images:

```bash
docker compose down
docker compose up -d --build
```

## Roadmap

Next development stage:

- Part B1 – Core Domain Model
- Mission Engine
- Vehicle Registry
- Sensor Registry
- Replay Engine
- SDK
- Environment Model

## Acknowledgements

Thanks to all contributors and early testers who helped validate the
Foundation release.
