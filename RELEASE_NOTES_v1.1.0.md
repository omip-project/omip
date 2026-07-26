# OMIP Core Platform v1.1.0

## Release status

Stable Release

OMIP v1.1.0 introduces the first consolidated repository-layer architecture
for the OMIP Core Platform.

## Highlights

- Dedicated API router modules for health and acquisition endpoints
- Vehicle Profile repository
- Scenario repository
- Obstacle repository
- Constraint repository
- External Field repository
- Mission Environment Snapshot repository
- Reduced direct persistence responsibilities in `EnvironmentContextService`
- Preserved API, database, MQTT, simulator and Docker compatibility

## Compatibility

- No breaking API changes
- No database migration required
- Existing schema version remains `0.5.2`
- Existing Docker Compose workflows remain supported
- Existing vehicle profiles, scenarios and mission data remain compatible

## Validation

The release candidate passed:

- Python compilation
- Full automated regression tests
- Docker image rebuild
- Backend and MQTT health checks
- Operations Console verification
- Swagger verification
- Demo simulator mission lifecycle
- Telemetry flow validation
- Persistence validation after restart

## Upgrade overview

1. Back up the SQLite database and runtime configuration.
2. Download or pull OMIP v1.1.0.
3. Rebuild the Docker services.
4. Start the backend and MQTT services.
5. Verify the Operations Console and Swagger.
6. Run the demo simulator.
7. Confirm existing scenarios and vehicle profiles remain accessible.