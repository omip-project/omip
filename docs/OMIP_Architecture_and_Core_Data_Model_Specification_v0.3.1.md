# OMIP Architecture and Core Data Model Specification v0.3.1

## 1. Purpose

OMIP v0.3.1 stabilises the v0.3 acquisition platform for longer-running simulation and later physical-device integration. The release introduces an explicit heartbeat channel, separates vehicle connectivity from sensor health, and distinguishes normal inactivity from communication failure.

## 2. Architectural principles

1. Raw sensor data is preserved before normalisation.
2. Vehicle connection status and sensor connection status are independent.
3. Mission lifecycle determines whether missing data means OFFLINE or INACTIVE.
4. Heartbeat is a connectivity signal, not a substitute for sensor data.
5. Acquisition failure should not block the simulator motion clock.
6. Message identifiers provide idempotency during retry.
7. OMIP observes and records; it does not control the vehicle.

## 3. Logical architecture

```text
Vehicle / Simulator
├── Heartbeat producer
├── GNSS producer
├── IMU producer
├── Battery producer
└── Vehicle-status producer
          |
          | HTTP or MQTT
          v
Acquisition Layer
├── Heartbeat ingestion
├── Raw-message ingestion
├── Telemetry ingestion
├── Schema validation
└── WebSocket stream
          |
          +-------------------+
          |                   |
          v                   v
Heartbeat Store        Raw Sensor Store
                              |
                              v
                       Baseline Normalizer
                              |
                              v
                       Telemetry Store
                              |
                 +------------+------------+
                 |                         |
                 v                         v
             Dashboard               Replay / Export
```

## 4. Mission-aware connection state

### 4.1 Vehicle state

Let:

- `M` be whether a mission for the vehicle is currently `RUNNING`.
- `E` be whether the vehicle registry entry is enabled.
- `A` be the age in seconds of the most recent server-received heartbeat or telemetry/raw-message activity.
- `T_online` be the online threshold, default 5 seconds.
- `T_degraded` be the degraded threshold, default 15 seconds.

The vehicle state is:

```text
not E                                  -> DISABLED
M and A <= T_online                    -> ONLINE
M and T_online < A <= T_degraded       -> DEGRADED
M and A > T_degraded                   -> OFFLINE
not M and prior mission/activity       -> INACTIVE
not M and no prior mission/activity    -> UNKNOWN
```

A completed or aborted mission therefore produces `INACTIVE`, even when the last data was received hours ago.

### 4.2 Sensor state

A sensor uses its own `last_seen_at_utc`, but it also observes whether the vehicle has a running mission:

```text
sensor disabled                             -> DISABLED
no running mission and prior data/mission   -> INACTIVE
running mission and recent sensor data      -> ONLINE
running mission and delayed sensor data     -> DEGRADED
running mission and stale sensor data       -> OFFLINE
no data and no mission history              -> UNKNOWN
```

A current vehicle heartbeat does not update the sensor's last-seen timestamp.

## 5. Heartbeat data contract

```json
{
  "schema_version": "0.3.1",
  "message_id": "UUID",
  "vehicle_id": "OMIP-SIM-001",
  "mission_id": "MISSION-001",
  "timestamp_utc": "2026-07-18T07:30:00.000+00:00",
  "state": "RUNNING",
  "source": "multi_sensor_simulator",
  "metadata": {
    "pending_messages": 0
  }
}
```

### 5.1 Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schema_version` | string | yes | Must be `0.3.1` |
| `message_id` | UUID | yes | Unique idempotency key |
| `vehicle_id` | string | yes | Registered vehicle |
| `mission_id` | string/null | no | Associated mission |
| `timestamp_utc` | timezone-aware datetime | yes | Producer time |
| `state` | enum | yes | `RUNNING`, `IDLE`, or `STOPPING` |
| `source` | string | yes | Heartbeat producer |
| `metadata` | object | no | Extension data |

## 6. Database additions

### 6.1 `vehicle_heartbeats`

```text
id                    INTEGER primary key
message_id            TEXT unique
vehicle_id            TEXT foreign key
mission_id            TEXT nullable foreign key
timestamp_utc          TEXT
received_at_utc        TEXT
state                  TEXT
transport              TEXT
source                 TEXT
metadata_json          TEXT
```

Indexes:

```text
(vehicle_id, received_at_utc DESC)
(mission_id, received_at_utc DESC)
```

No heartbeat is written into a sensor row. This maintains the separation between vehicle connectivity and sensor health.

## 7. Reliable simulator publisher

The simulator uses a bounded in-memory queue and a background worker.

### 7.1 Message lifecycle

```text
SUBMITTED
   |
   v
QUEUED
   |
   v
SEND ATTEMPT
   |----------------------|
   v                      v
SUCCESS              TEMPORARY FAILURE
                          |
                          v
                 EXPONENTIAL BACKOFF
                          |
                    retry limit?
                    |          |
                   no         yes
                    |          |
                  QUEUED     DROPPED
```

### 7.2 Idempotency

Raw messages and heartbeats use unique `message_id` values. A retry that receives HTTP `409 Conflict` is treated as an idempotent success because the original message is already stored.

### 7.3 Backoff

For retry attempt `n`, the delay is:

```text
min(30 seconds, retry_base * 2^(n-1))
```

The default retry base is 0.5 seconds.

### 7.4 Buffer boundary

When the queue reaches `max_buffer`, the oldest queued item is dropped before the new item is inserted. This prevents unbounded memory growth. Persistent store-and-forward is outside the v0.3.1 scope.

## 8. Continuous execution

Duration resolution is:

```text
CLI duration supplied     -> use CLI value
CLI duration omitted      -> use scenario default
resolved duration <= 0    -> continuous execution
resolved duration > 0     -> fixed-duration execution
```

On fixed-duration completion:

```text
heartbeat STOPPING
flush queue
mission -> COMPLETED
vehicle -> INACTIVE
```

On `Ctrl+C` or termination signal:

```text
heartbeat STOPPING
flush queue
mission -> ABORTED
vehicle -> INACTIVE
```

## 9. API additions

```text
POST /api/v1/vehicles/{vehicle_id}/heartbeat
GET  /api/v1/vehicles/{vehicle_id}/heartbeats?limit=100
```

Vehicle registry responses now include:

```text
active_mission_id
latest_mission_id
latest_mission_status
last_heartbeat_received_at_utc
last_heartbeat_timestamp_utc
last_heartbeat_state
last_heartbeat_transport
heartbeat_count
last_activity_at_utc
connection_status
connection_status_reason
activity_age_s
```

Sensor responses now include:

```text
active_mission_id
latest_mission_status
connection_status
connection_status_reason
activity_age_s
```

## 10. MQTT topics

```text
omip/{vehicle_id}/sensors/{sensor_id}
omip/{vehicle_id}/telemetry
omip/{vehicle_id}/heartbeat
```

Default subscriptions:

```text
omip/+/sensors/+
omip/+/telemetry
omip/+/heartbeat
```

## 11. Compatibility

- Existing v0.3 raw messages remain accepted.
- Existing v0.2 and v0.3 telemetry frames remain accepted.
- New v0.3.1 frames use schema version `0.3.1`.
- v0.2 mission, telemetry, replay and export endpoints remain available.
- Existing databases are extended using `CREATE TABLE IF NOT EXISTS`; the heartbeat table is additive.

## 12. Verification criteria

The release is considered complete when all of the following are demonstrated:

1. A running vehicle with recent heartbeat is ONLINE.
2. A running vehicle becomes DEGRADED and then OFFLINE when heartbeat and data stop.
3. A GNSS sensor can be OFFLINE while vehicle heartbeat keeps the vehicle ONLINE.
4. A completed mission changes vehicle and sensors to INACTIVE.
5. `--duration 0` continues until interrupted.
6. Temporary publish failure causes retry rather than immediate message loss.
7. The retry queue is bounded and reports drop statistics.
8. HTTP heartbeat ingestion and history retrieval work.
9. MQTT bridge subscribes to the heartbeat topic.
10. Existing v0.3 acquisition and export functionality remains operational.
