# OMIP Roadmap

This roadmap describes capability goals rather than fixed delivery dates.

## v1.1 Core Architecture

### Completed

- [x] API router separation
- [x] Vehicle profile repository
- [x] Scenario repository
- [x] Obstacle repository
- [x] Constraint repository
- [x] External field repository
- [x] Mission environment snapshot repository
- [x] v1.1.0 release-candidate identity

### Deferred

- [ ] Mission service extraction
- [ ] Shared repository JSON serialization
- [ ] Expanded direct repository unit-test coverage

### Release preparation

- [x] Version and identity update
- [x] Changelog and release notes
- [x] Full regression validation
- [x] Release candidate tag
- [x] Final v1.1.0 release

## Foundation v1.0

- Professional repository homepage
- Project identity and branding
- MIT licence review
- Contribution and community policies
- Issue and pull-request templates
- Continuous integration
- Docker deployment baseline
- MkDocs documentation website
- Citation metadata
- First public Foundation release

## Community Preview

- Stable Vehicle, Sensor, Mission and Telemetry contracts
- Vehicle Profile validation
- Scenario and Environment Context tooling
- Reliable historical replay
- Complete Mission export format
- Local deployment and backup workflow
- Public example missions

## Community Edition 1.0

- Versioned public API
- Database migration strategy
- Python SDK
- Production-ready Docker Compose
- Authentication baseline
- Dataset packaging and validation
- Supported upgrade process
- Public documentation website

## Research track

The research track remains experimental and separate from stable core contracts.

Planned areas:

- Trajectory event detection
- Unknown-obstacle inference
- External-force estimation
- Probabilistic Cause Fields
- Cause disambiguation
- Natural-language mission explanations
- Digital-twin integration
- Multi-agent mission analysis
- Foundation-model research

## Deployment track

- Local Docker deployment
- Linux LAN server
- HTTPS and secure MQTT
- PostgreSQL migration
- Object storage for exports and datasets
- Cloud deployment reference architecture
- Monitoring and backup automation

## SDK and integration track

- Python SDK
- .NET SDK
- ROS 2 bridge
- MQTT client examples
- Sensor adapter framework
- Autoware, PX4 and ArduPilot integration examples

## Out of scope for the current Foundation phase

- Certified safety control
- Direct vehicle actuation
- High-availability production clusters
- Commercial fleet-management features
- Claims of guaranteed collision avoidance
