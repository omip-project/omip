# OMIP Architecture and Core Data Model Specification v0.3

**Version:** 0.3  
**Status:** Starter implementation  
**Scope:** Multi-vehicle acquisition, raw sensor storage, normalization and event annotation

## 1. Purpose

OMIP v0.3 defines the acquisition boundary between heterogeneous vehicle data sources and later replay, analytics and research modules. The platform must preserve original observations while providing a stable normalized telemetry contract.

The central architectural rule is:

> Raw source data and normalized platform data are different records and must not be treated as interchangeable.

This protects provenance and makes future normalizers, filters and fusion algorithms replaceable.

## 2. Version objectives

v0.3 shall:

1. Register multiple vehicles.
2. Register multiple sensors for each vehicle.
3. accept raw sensor data through HTTP and MQTT;
4. store each accepted raw message with transport metadata and server receive time;
5. normalize supported position messages into the common telemetry model;
6. track vehicle and sensor availability;
7. associate all collected data with a mission;
8. support event annotations for research and evaluation;
9. retain v0.2 mission, replay, quality and export capabilities;
10. avoid vehicle command and control functionality.

## 3. System context

```text
+----------------------+       +----------------------+
| Vehicle / Simulator  |       | File or Batch Client |
| GNSS IMU Battery ... |       | Historical messages  |
+----------+-----------+       +-----------+----------+
           | HTTP / MQTT                   | HTTP batch
           +---------------+---------------+
                           v
                +----------------------+
                | Acquisition Layer    |
                | validate / timestamp |
                | provenance / route   |
                +----+-------------+---+
                     |             |
                     v             v
              Raw Message      Normalizer
                 Store             |
                                   v
                            Telemetry Store
                                   |
                +------------------+------------------+
                |                  |                  |
             WebSocket          Replay             Export
```

## 4. Logical components

### 4.1 Registry service

The registry service stores stable metadata about vehicles and their sensors. A vehicle or sensor can be disabled without deleting historical records.

### 4.2 HTTP ingestor

The HTTP ingestor accepts one raw message or a batch. It validates the schema, records receive time and transport, stores the original message, and passes it to the normalizer.

### 4.3 MQTT bridge

The MQTT bridge subscribes to configurable wildcard topics and converts JSON payloads into the same internal ingestion path used by HTTP. MQTT does not have a separate storage model.

Default topics:

```text
omip/+/sensors/+
omip/+/telemetry
```

### 4.4 Raw message repository

The repository stores the source payload plus acquisition metadata:

- receive timestamp;
- calculated latency;
- transport;
- MQTT topic where applicable;
- validation state and confidence.

### 4.5 Baseline normalizer

The v0.3 normalizer maintains the latest IMU, battery and vehicle-status values for each `(vehicle_id, mission_id)` pair. A GNSS or odometry message triggers a normalized telemetry output using that cached state.

This behavior is deterministic and transparent, but it is not a substitute for a Kalman filter or production sensor-fusion system.

### 4.6 WebSocket service

Two channels are retained:

```text
/ws/telemetry  legacy normalized-telemetry stream
/ws/stream     typed raw and normalized envelopes
```

The typed stream emits:

```json
{"stream_type":"raw_sensor","data":{}}
```

or:

```json
{"stream_type":"telemetry","data":{}}
```

### 4.7 Event annotation service

Events label an interval or point in mission time. Sources can be manual, simulator, system or imported. Events are separate from raw messages and do not alter source data.

## 5. Core entities

### 5.1 Vehicle

| Field | Type | Notes |
|---|---|---|
| vehicle_id | string | Stable unique identifier |
| vehicle_name | string | Human-readable name |
| vehicle_type | enum | Ground vehicle, AUV, USV, UAV, simulated or other |
| manufacturer | string | Optional |
| model | string | Optional |
| enabled | boolean | Disabled vehicles retain history |
| metadata | JSON object | Extensible metadata |
| last_seen_at_utc | timestamp | Server receive time of latest data |

### 5.2 Sensor

| Field | Type | Notes |
|---|---|---|
| sensor_id | string | Globally unique in v0.3 |
| vehicle_id | string | Owning vehicle |
| sensor_type | enum | GNSS, IMU, odometry, battery, status or generic |
| sampling_rate_hz | number | Declared nominal rate |
| coordinate_frame | string | Sensor frame description |
| enabled | boolean | Operational registry state |
| last_transport | string | HTTP, MQTT, file upload or simulator |
| message_count | integer | Accepted raw-message count |
| invalid_message_count | integer | Accepted messages marked invalid |

### 5.3 Mission

A mission provides the collection context for raw and normalized data. States remain:

```text
PLANNED -> RUNNING -> COMPLETED
                 \-> ABORTED
PLANNED ----------------> ABORTED
```

### 5.4 RawSensorMessage

```json
{
  "schema_version": "0.3",
  "message_id": "uuid",
  "vehicle_id": "string",
  "sensor_id": "string",
  "mission_id": "string",
  "sequence_no": 0,
  "timestamp_utc": "timezone-aware ISO 8601",
  "message_type": "GNSS|IMU|ODOMETRY|BATTERY|VEHICLE_STATUS|GENERIC",
  "payload": {},
  "quality": {
    "valid": true,
    "position_source": "SIMULATED",
    "confidence": 1.0
  }
}
```

Server-added fields are:

```text
received_at_utc
latency_ms
transport
topic
```

### 5.5 TelemetryFrame

The normalized telemetry model contains:

- position;
- velocity;
- acceleration;
- orientation;
- vehicle state;
- quality;
- source and coordinate frame.

v0.3 accepts both schema versions `0.2` and `0.3` for backward compatibility. New normalizer outputs use `0.3`.

### 5.6 MissionEvent

| Field | Type | Notes |
|---|---|---|
| event_id | string | Generated or client supplied |
| mission_id | string | Required |
| vehicle_id | string | Must match mission vehicle |
| event_type | string | Extensible label |
| start_timestamp_utc | timestamp | Required |
| end_timestamp_utc | timestamp | Optional interval end |
| severity | enum | Info, warning or critical |
| source | enum | Manual, simulator, system or imported |
| description | string | Human-readable explanation |
| metadata | JSON object | Extensible values |

## 6. Database model

v0.3 uses SQLite with WAL mode for a local starter implementation.

Tables:

```text
vehicles
sensors
missions
raw_sensor_messages
telemetry
mission_events
```

The raw and normalized tables each have their own unique `message_id`. A normalized message generated from raw input receives a new UUID and references the originating sensor in its `source` field.

## 7. Acquisition sequence

For a raw HTTP message:

```text
1. Pydantic validates RawSensorMessage.
2. Registry ownership is checked or an acquisition-compatible entry is created.
3. Mission association is checked.
4. Server receive time and latency are calculated.
5. Original raw message is inserted.
6. Vehicle and sensor last-seen counters are updated.
7. Raw message is broadcast on /ws/stream.
8. Normalizer updates cached state.
9. GNSS/odometry may create TelemetryFrame.
10. Telemetry is stored and broadcast.
```

MQTT follows the same sequence after JSON decoding.

## 8. Status model

Availability is derived from server receive time, not the source timestamp. This prevents a delayed source clock from incorrectly making a currently connected sensor appear offline.

Default thresholds:

```text
ONLINE     age <= 5 s
DEGRADED   5 s < age <= 15 s
OFFLINE    age > 15 s
DISABLED   registry enabled = false
UNKNOWN    last_seen_at_utc is null
```

## 9. Quality metrics

Mission telemetry and individual sensor streams support:

- total messages;
- first and last sequence number;
- missing sequence count;
- out-of-order or duplicate sequence count;
- invalid frame count;
- average confidence;
- average rate;
- average and maximum latency;
- duration.

These are observational metrics. They do not repair or delete data.

## 10. Simulator model

The simulator generates four independent streams with configurable rates. The nominal defaults are 5 Hz GNSS, 20 Hz IMU, 1 Hz battery and 2 Hz vehicle status.

Supported scenario faults include:

- GNSS message suppression;
- timestamp delay;
- periodic invalid frames;
- periodic IMU spikes;
- duplicate message attempts;
- out-of-order sequence values;
- return-to-base status transitions.

## 11. Compatibility

v0.3 preserves:

- `/api/v1/telemetry`;
- `/ws/telemetry`;
- mission lifecycle endpoints;
- mission telemetry history;
- quality summary;
- telemetry CSV and JSONL export.

If an earlier database is copied into the backend, the repository creates the new registry and raw/event tables and backfills basic vehicle records from existing missions or telemetry.

## 12. Security and deployment limits

The starter implementation permits anonymous local HTTP and MQTT access. CORS is unrestricted. Mosquitto permits anonymous access in the supplied development configuration.

Production deployment requires at least:

- authenticated API clients;
- TLS for HTTP and MQTT;
- broker credentials and topic authorization;
- controlled CORS origins;
- rate limits and payload-size limits;
- database backup and retention policies;
- migration tooling beyond automatic starter migrations.

## 13. Acceptance criteria

v0.3 is complete when the reference implementation can:

1. register two vehicles;
2. register multiple sensors per vehicle;
3. receive independent raw sensor streams;
4. preserve raw messages with provenance;
5. produce normalized telemetry from GNSS/odometry;
6. show sensor availability changes after messages stop;
7. annotate mission events;
8. query sensor quality;
9. export raw and normalized data;
10. operate through HTTP alone or through the optional MQTT stack.

## 14. Deferred work

The following are outside v0.3:

- vehicle command/control;
- video and LiDAR bulk streaming;
- ROS 2 bridge;
- advanced time synchronization;
- probabilistic sensor fusion;
- automatic event detection;
- dataset versioning and train/test partitioning;
- production identity and access management.
