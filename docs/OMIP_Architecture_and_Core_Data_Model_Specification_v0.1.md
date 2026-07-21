# OMIP Architecture and Core Data Model Specification v0.1

**Status:** Initial baseline  
**Approach:** Simulation-first  
**Primary purpose:** Collect, transport, store, visualise, replay, and analyse autonomous-vehicle operational data.

## 1. Scope

OMIP v0.1 establishes a small but complete platform rather than attempting a full autonomous-driving stack. It does not control a vehicle, perform perception, or make safety-critical driving decisions. Its role is to provide a reliable data foundation on which simulation, monitoring, analytics, anomaly detection, explanation, and future research modules can be built.

The first usable system must accept telemetry from a simulated vehicle, store it with stable identifiers and timestamps, display the latest state in real time, and retrieve historical records for replay or analysis.

## 2. Design principles

1. **Simulation before hardware.** All core functions must be testable without purchasing a vehicle or sensors.
2. **Data contracts before advanced algorithms.** Stable schemas and timestamps are more important than early AI features.
3. **Separation of collection and interpretation.** Raw telemetry must remain available even when later analytics models change.
4. **Replaceable data sources.** The simulator, a real vehicle, recorded files, and third-party systems should use the same ingestion boundary.
5. **Incremental architecture.** v0.1 should run on one computer while preserving a path to distributed deployment.
6. **Traceability.** Every telemetry message must identify its vehicle, mission, sequence number, source, and time.

## 3. v0.1 system context

```text
+-------------------+        HTTP/JSON         +---------------------+
| Vehicle Simulator | -----------------------> | Telemetry Ingestion |
+-------------------+                          | API                 |
                                               +----------+----------+
                                                          |
                                                          v
                                               +---------------------+
                                               | SQLite Telemetry DB |
                                               +----------+----------+
                                                          |
                                     +--------------------+--------------------+
                                     |                                         |
                                     v                                         v
                          +---------------------+                    +---------------------+
                          | WebSocket Live Feed |                    | History Query API   |
                          +----------+----------+                    +----------+----------+
                                     |                                         |
                                     +--------------------+--------------------+
                                                          v
                                               +---------------------+
                                               | Browser Dashboard   |
                                               +---------------------+
```

## 4. Logical components

### 4.1 Telemetry source

A telemetry source generates or forwards vehicle state. In v0.1 the source is a Python simulator. Future sources may include a ROS 2 bridge, CAN gateway, GNSS receiver, recorded log importer, or physical test vehicle.

### 4.2 Telemetry ingestion API

The API validates the message schema, rejects duplicate message identifiers, timestamps receipt, persists the record, and publishes it to connected live clients.

### 4.3 Persistence

SQLite is sufficient for a single-computer proof of concept. The schema isolates the application from the storage choice so that PostgreSQL or a time-series extension can replace SQLite in a later version.

### 4.4 Live data channel

WebSocket delivery allows dashboards and development tools to observe new frames without repeatedly polling the server.

### 4.5 Query and replay boundary

The history endpoint returns ordered telemetry for a selected vehicle. v0.2 will add time-range filtering, mission filtering, pagination, replay speed, and export.

## 5. Core domain entities

### 5.1 Vehicle

Represents a unique physical or simulated mobile platform.

| Field | Type | Description |
|---|---|---|
| vehicle_id | string | Stable unique identifier |
| display_name | string | Human-readable name |
| vehicle_type | string | Car, rover, AUV, drone, simulator, or other type |
| status | string | Registered, active, inactive, maintenance |
| created_at_utc | timestamp | Registration time |

### 5.2 Mission

Groups telemetry generated for one experiment, route, or operational session.

| Field | Type | Description |
|---|---|---|
| mission_id | string | Stable mission identifier |
| vehicle_id | string | Assigned vehicle |
| name | string | Human-readable mission name |
| started_at_utc | timestamp | Mission start |
| ended_at_utc | timestamp, nullable | Mission end |
| status | string | Planned, running, completed, aborted |
| scenario | string, nullable | Simulation or operating scenario |

### 5.3 TelemetryFrame

The atomic time-stamped record sent by a source.

| Group | Main fields |
|---|---|
| Identity | schema_version, message_id, vehicle_id, mission_id, sequence_no |
| Time | timestamp_utc, received_at_utc |
| Source | source, coordinate_frame |
| Position | x_m, y_m, z_m, optional latitude_deg and longitude_deg |
| Velocity | vx_mps, vy_mps, vz_mps, speed_mps |
| Acceleration | ax_mps2, ay_mps2, az_mps2 |
| Orientation | heading_deg, pitch_deg, roll_deg |
| Vehicle state | battery_percent, operating_mode, autonomy_enabled, emergency_stop |
| Quality | valid, position_source, confidence |

### 5.4 SensorObservation

Reserved for measurements that should not be forced into the vehicle-state record, such as lidar detections, camera metadata, ultrasonic range, wheel encoder data, current measurements, or environmental observations.

### 5.5 EventAnnotation

Represents a human-generated or algorithm-generated interpretation over a time interval. Examples include obstacle avoidance, strong current influence, communication loss, emergency braking, or suspected sensor fault.

| Field | Type | Description |
|---|---|---|
| event_id | string | Unique event identifier |
| mission_id | string | Related mission |
| start_time_utc | timestamp | Event start |
| end_time_utc | timestamp | Event end |
| event_type | string | Classified event |
| confidence | number | Confidence from 0 to 1 |
| source | string | Human, rule, model, or imported label |
| explanation | text | Optional natural-language explanation |

## 6. Telemetry JSON contract v0.1

```json
{
  "schema_version": "0.1",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "vehicle_id": "OMIP-SIM-001",
  "mission_id": "MISSION-001",
  "sequence_no": 42,
  "timestamp_utc": "2026-07-18T04:30:00.000Z",
  "source": "python-simulator",
  "coordinate_frame": "LOCAL_ENU",
  "position": { "x_m": 14.2, "y_m": 3.8, "z_m": 0.0 },
  "velocity": { "vx_mps": 1.2, "vy_mps": 0.1, "vz_mps": 0.0, "speed_mps": 1.204 },
  "acceleration": { "ax_mps2": 0.0, "ay_mps2": -0.02, "az_mps2": 0.0 },
  "orientation": { "heading_deg": 4.8, "pitch_deg": 0.0, "roll_deg": 0.0 },
  "state": {
    "battery_percent": 96.4,
    "operating_mode": "AUTONOMOUS_MISSION",
    "autonomy_enabled": true,
    "emergency_stop": false
  },
  "quality": { "valid": true, "position_source": "SIMULATED", "confidence": 1.0 }
}
```

## 7. Interface requirements

### POST /api/v1/telemetry

Accepts one `TelemetryFrame`. The service validates the contract, stores the message, and publishes the stored frame to live clients.

Expected responses:

- `201 Created`: accepted and stored
- `409 Conflict`: duplicate `message_id`
- `422 Unprocessable Entity`: invalid schema or field value

### GET /api/v1/vehicles

Returns vehicles currently represented in the telemetry store, the latest telemetry timestamp, and the number of stored frames.

### GET /api/v1/vehicles/{vehicle_id}/latest

Returns the latest stored frame for a vehicle.

### GET /api/v1/vehicles/{vehicle_id}/telemetry

Returns ordered historical frames. v0.1 supports a record limit. Future versions will support time and mission filters.

### WS /ws/telemetry

Pushes newly accepted telemetry frames to connected clients.

## 8. Non-functional baseline

- All event times use timezone-aware UTC.
- `message_id` is globally unique and supports safe retries.
- `sequence_no` supports missing-frame and ordering analysis.
- Raw received content is preserved as JSON.
- Invalid frames do not enter the database.
- The v0.1 service is intended for development and research, not safety-critical production deployment.

## 9. Out of scope for v0.1

- Vehicle actuation or remote control
- Autonomous planning and perception
- Safety certification
- User authentication and authorisation
- Multi-tenant cloud deployment
- High-availability infrastructure
- Video streaming
- Large binary sensor payloads
- AI explanation generation

## 10. Version roadmap

### v0.1 — Data path proof

Simulator, ingestion, validation, storage, live display, and basic history.

### v0.2 — Experiment platform

Mission records, scenario configuration, data export, replay, time-range queries, and data-quality checks.

### v0.3 — Extensible mobility data platform

Pluggable source adapters, ROS 2 bridge, event detection, annotation, richer dashboards, and PostgreSQL deployment.

### v0.4 — Intelligence layer

Anomaly detection, cause inference, explanation modules, experiment comparison, and model evaluation. These modules consume stored OMIP data but do not replace the raw-data layer.

## 11. v0.1 acceptance test

1. Start the API on a development computer.
2. Open the dashboard in a browser.
3. Start the simulator.
4. Confirm that the dashboard updates within one second.
5. Stop and restart the simulator with the same vehicle identifier.
6. Confirm that new records are appended and history remains available.
7. Query the latest and history endpoints from the generated API documentation.
8. Verify that re-sending an existing `message_id` returns `409 Conflict`.
