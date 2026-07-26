## [1.1.0] - 2026-07-26

### Release

- Promoted OMIP v1.1.0-rc1 to the stable v1.1.0 release.
- Completed repository-layer architecture validation.
- Updated backend, simulator, health API and Operations Console identities.
- Added final v1.1.0 release documentation.

### Compatibility

- No breaking API changes.
- No database migration required.
- Existing schema version remains 0.5.2.
- Existing Docker, MQTT, dashboard and simulator workflows are preserved.

## [1.1.0-rc1] - 2026-07-26

### Added

- Added API router separation for health and acquisition endpoints.
- Added a dedicated repository layer for vehicle profiles.
- Added `ScenarioRepository`.
- Added `ObstacleRepository`.
- Added `ConstraintRepository`.
- Added `ExternalFieldRepository`.
- Added `MissionEnvironmentSnapshotRepository`.

### Changed

- Refactored environment persistence out of `EnvironmentContextService`.
- Delegated scenario, obstacle, constraint, external-field and mission-snapshot
  database operations to dedicated repositories.
- Updated runtime identity to OMIP v1.1.0-rc1.
- Preserved existing API paths, database schema and MQTT behaviour.

### Compatibility

- No breaking API changes.
- No database migration required.
- Existing Docker Compose workflow remains supported.
- Existing simulator and dashboard workflows remain supported.

### Known Issues

- The safety analytics test fixture may require a valid
  `geometry_type` when supplying constraint geometry.
- Shared JSON serialization remains implemented in individual repositories
  and may be consolidated in a future maintenance release.

## [1.0.1-foundation] - 2026-07-24

### Fixed

- Changed the default Docker host port from `8000` to `18080`.
- Improved compatibility with Windows reserved TCP port ranges.
- Updated README, Quick Start and troubleshooting documentation.

# v0.5.2.1

- Added multi-direction candidate avoidance and all-obstacle validation.
- Added automatic offset expansion with a configurable hard limit.
- Added emergency-stop/hold-position fallback for blocked routes.
- Added avoidance direction, predicted clearance and failure telemetry.
- Added large-obstacle and two-obstacle safety scenarios and tests.

# OMIP Changelog

## v0.5.2

- Added vehicle-specific safety-envelope calculation.
- Added nearest-obstacle clearance, closing-speed and TTC estimates.
- Added persistent obstacle interaction records and Mission summaries.
- Added automatic `OBSTACLE_AVOIDANCE` and `COLLISION_RISK` Mission Events.
- Added UGV, UAV, AUV and USV obstacle-aware trajectory behaviour.
- Added moving-obstacle position handling.
- Added Dashboard risk panel and safety-envelope overlay.
- Added `obstacle_avoidance` Scenario settings and database migration.
- Added four obstacle-interaction demonstration Scenarios.
- Added obstacle interaction data to Mission ZIP exports.
- Added v0.5.2 regression and API tests.

# Changelog

## v0.5.1

- Added the Environment Context Layer.
- Added versioned Scenario templates.
- Added obstacles with point, circle, sphere, box and polygon geometry.
- Added vehicle-specific operational and spatial constraints.
- Added wind, current and other external-field models.
- Added applicability filtering by vehicle type, Vehicle ID and capability.
- Added immutable Mission Environment Snapshots with SHA-256 checksums.
- Added environment CRUD and Mission snapshot APIs.
- Added the Dashboard Environment Context editor and XY/XZ/YZ overlays.
- Added basic wind/current drift and speed/altitude/depth constraint handling.
- Added environment capture for browser and direct CLI runs.
- Added `environment.json` to Mission export packages.
- Added four environment-aware Scenario examples.
- Added v0.5.1 environment regression tests.

# OMIP Changelog

## v0.5.0

- Added storage summary, table counts and database growth estimation.
- Added paginated Mission Telemetry, Raw Message and Application Log APIs.
- Added configurable retention policy, cleanup preview and manually confirmed cleanup.
- Added safe Mission delete preview and confirmation-based cascade deletion.
- Added persistent background export jobs and downloadable results.
- Added SQLite backups with checksums.
- Added integrity check, ANALYZE, WAL checkpoint and manual VACUUM.
- Added Storage Management, Export Jobs and Backup panels.
- Added v0.5.0 storage lifecycle regression tests.

# Changelog

## v0.4.2

- Added SystemHealthService and RuntimeMetricsService.
- Added backend, database, MQTT, WebSocket, ingestion, integrity-engine and process component health.
- Added rolling 10-second, 1-minute and 5-minute message rates.
- Added separate HTTP and MQTT ingestion counters.
- Added database write/query latency and failure counters.
- Added structured application_logs persistence and filtering APIs.
- Added periodic system_metric_snapshots with configurable retention.
- Added platform_alerts with acknowledge, manual resolve and automatic recovery.
- Added SQLite health, file size, response time and table row statistics.
- Added process memory and CPU statistics through psutil.
- Added System Monitoring, Component Health, Platform Alerts and Application Logs dashboard panels.
- Added high-message-rate, invalid-payload and database-lock test utilities.
- Added v0.4.2 operational monitoring regression tests.

## v0.4.1

- Added LOW_SAMPLING_RATE and HIGH_SAMPLING_RATE detection.
- Added HIGH_LATENCY warning and critical thresholds.
- Added TIMESTAMP_REGRESSION, FUTURE_TIMESTAMP and CLOCK_DRIFT checks.
- Added sliding-window rate evaluation using Sensor Registry sampling rates.
- Added per-Sensor and per-Mission integrity metrics APIs.
- Added average, P50, P95 and maximum latency calculations.
- Added automatic resolution for recoverable timing and rate Alerts.
- Added Alert resolution source and reason fields with database migration.
- Added Sensor Integrity Metrics to the Operations Console.
- Added integrity-metrics.json to complete Mission ZIP exports.
- Added low-rate, high-latency, timestamp and combined timing fault scenarios.
- Added v0.4.1 timing, recovery and export regression tests.

## v0.4.0

- Added persistent Integrity Events and operational Alerts.
- Added restart-safe sequence state using SQLite queries.
- Added Sequence Gap detection.
- Added duplicate message-ID and duplicate sequence-number detection.
- Added Out-of-Order detection.
- Added active Alert aggregation with occurrence counts.
- Added OPEN, ACKNOWLEDGED and RESOLVED alert lifecycle.
- Added Integrity Event and Alert REST APIs.
- Added Mission integrity summary API.
- Added integrity and alert WebSocket messages.
- Added Dashboard monitoring and Alert actions.
- Added integrity-events.json and alerts.json to complete Mission ZIP exports.
- Added automated integrity and alert regression tests.

## v0.3.4

- Fixed Mission selection being reset or appearing unresponsive during periodic refresh.
- Added visible Mission loading, ready and error states.
- Added an explicit Load mission button.
- Enabled export links immediately after selection.
- Loaded telemetry, raw messages and events independently with partial-failure handling.
- Limited Dashboard previews while preserving complete exports.
- Improved API error messages shown in the Dashboard.

## v0.3.3

- Added a visible Data Export panel to the Dashboard.
- Added one-click telemetry CSV/JSONL and raw sensor CSV/JSONL downloads.
- Added a complete mission ZIP export containing mission metadata, quality summary, events, telemetry and raw messages.
- Added Z-coordinate display to the live telemetry panel.
- Added XY, XZ and YZ trajectory projection controls.
- Fixed the hidden export-link design in v0.3.2.

# OMIP Changelog

## v0.3.1

- Added continuous simulator mode with `--duration 0` or a negative duration.
- Added `VehicleHeartbeat` schema v0.3.1.
- Added HTTP heartbeat ingestion and heartbeat history endpoints.
- Added MQTT heartbeat topic support.
- Added `vehicle_heartbeats` persistence and indexes.
- Added mission-aware `INACTIVE` connection state.
- Separated vehicle connectivity from individual sensor health.
- Added status reason, activity age, active mission and heartbeat fields to registry responses.
- Added bounded background publishing queue.
- Added exponential retry and idempotent duplicate handling.
- Added shutdown queue-drain handling and publisher delivery counters.
- Updated dashboard for heartbeat and mission-aware status display.
- Added tests for heartbeat, sensor/vehicle status separation, inactive state and retry recovery.

## v0.3.0

- Added formal vehicle registry.
- Added formal sensor registry.
- Added raw sensor message schema v0.3.
- Added HTTP single-message and batch ingestion.
- Added optional MQTT consumer and topic structure.
- Added raw-message provenance storage.
- Added stateful baseline normalizer.
- Added sensor and vehicle connection status.
- Added sensor quality summaries.
- Added mission event annotation CRUD.
- Added raw CSV and JSONL exports.
- Added multi-sensor simulator and fault scenarios.
- Added acquisition dashboard.
- Added Docker Compose stack with Mosquitto.
- Preserved v0.2 telemetry and mission endpoints.

## v0.2.0

- Added mission lifecycle.
- Added configurable scenarios.
- Added replay, quality metrics and exports.

## v0.1.0

- Added simulator-to-API telemetry pipeline.
- Added SQLite storage, WebSocket streaming and live trajectory page.

## v0.3.2

- Fixed fleet summary cards so they always show global vehicle and sensor totals.
- Removed automatic vehicle selection caused by incoming telemetry.
- Added fleet-view multi-vehicle trajectories and stable raw-message filtering.
- Added runtime MQTT enable, disable and reconfiguration API.
- Added MQTT controls to the Operations Console.
- Added no-cache dashboard response for development upgrades.
- Added MQTT broker start/stop helper scripts.
- Added runtime MQTT and dashboard regression tests.

## v0.5.0

- Added vehicle type catalogue and parameter definitions.
- Added versioned Vehicle Profile registry.
- Added built-in UGV, UAV, AUV and USV profiles.
- Added vehicle capabilities and effective parameter snapshots.
- Added persisted Simulation Run lifecycle and local worker management.
- Added Operations Console vehicle type/profile/scenario selection.
- Added simulator CLI arguments for type, profile, overrides and random seed.
- Added vehicle-specific planar and three-dimensional trajectory generation.
- Added Mission reproducibility metadata.
