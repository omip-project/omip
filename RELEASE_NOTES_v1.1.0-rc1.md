# OMIP Core Platform v1.1.0-rc1

## Release status

Release Candidate

This release candidate introduces the first consolidated repository-layer
architecture for the OMIP Core Platform. It is intended for validation before
the final v1.1.0 release.

## Highlights

### API router separation

Health and acquisition endpoints are registered through dedicated router
modules, reducing the responsibilities of the main application module.

### Repository layer

The following repositories are now available:

- `VehicleProfileRepository`
- `ScenarioRepository`
- `ObstacleRepository`
- `ConstraintRepository`
- `ExternalFieldRepository`
- `MissionEnvironmentSnapshotRepository`

### Environment service refactoring

`EnvironmentContextService` retains environment-domain orchestration while
delegating SQLite persistence to dedicated repositories.

The service continues to manage:

- scenario validation;
- scenario version updates;
- scenario JSON export;
- applicability filtering;
- mission environment snapshot construction;
- canonical JSON generation;
- snapshot SHA-256 generation.

### Compatibility

This release candidate does not intentionally change:

- API paths;
- request or response schemas;
- database table structures;
- MQTT topics;
- simulator startup parameters;
- dashboard workflows;
- Docker Compose workflows.

No database migration is required from OMIP Foundation v1.0.1.

## Validation completed

- Python compilation
- Environment-context tests
- Obstacle-interaction tests
- Repository regression tests
- Docker image rebuild
- Backend health check
- MQTT health check
- Dashboard verification
- Swagger verification
- Demo simulator mission run

## Known issues

The safety analytics test fixture may need to provide a valid
`geometry_type` when constraint geometry is present.

Shared JSON serialization is still implemented separately in several
repositories. Consolidation has been deferred because it is not required for
the v1.1.0 release.

## Upgrade overview

1. Back up the current SQLite database and runtime configuration.
2. Pull or extract the v1.1.0-rc1 source.
3. Rebuild the Docker services.
4. Start the backend and MQTT services.
5. Verify `/health`, Swagger and the Operations Console.
6. Run the demo simulator.
7. Confirm existing scenarios and vehicle profiles remain accessible.

## Release candidate feedback

Report defects through the repository issue tracker with:

- operating system;
- Docker version;
- command used;
- relevant logs;
- reproduction steps;
- expected and actual behaviour.