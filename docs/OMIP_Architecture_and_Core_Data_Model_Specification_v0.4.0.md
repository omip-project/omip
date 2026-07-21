# OMIP Architecture and Core Data Model Specification v0.4.0

## 1. Purpose

OMIP v0.4.0 introduces the first operational data-integrity layer. The acquisition architecture remains compatible with v0.3.4, while each persisted raw-sensor and normalised-telemetry message is now evaluated for sequence continuity.

The first supported checks are:

1. `SEQUENCE_GAP`
2. `DUPLICATE_MESSAGE`
3. `OUT_OF_ORDER`

Each detected fault becomes a persistent Integrity Event and may create or update an operational Alert.

## 2. Processing architecture

```text
HTTP / MQTT message
        |
        v
Schema validation
        |
        v
DataIntegrityService -----> Repository sequence state
        |                         |
        |                         +-- previous maximum sequence
        |                         +-- existing sequence number
        |                         +-- existing message ID
        v
Primary message storage
        |
        +-- raw_sensor_messages
        +-- telemetry
        |
        v
Persist Integrity Events
        |
        v
Create or update Alerts
        |
        +-- REST API
        +-- WebSocket stream
        +-- Operations Console
```

The integrity service does not rely on process-local sequence counters. It obtains the last persisted state from SQLite before evaluating a message. This makes detection restart-safe and allows copied databases to retain their sequence baseline.

## 3. Stream identity

### 3.1 Raw sensor stream

```text
stream_kind = RAW_SENSOR
stream identity = mission_id + sensor_id
```

Each registered sensor has an independent sequence history during a Mission.

### 3.2 Normalised telemetry stream

```text
stream_kind = TELEMETRY
stream identity = mission_id + vehicle_id
```

This stream records the output of the normalisation layer or a direct Telemetry client.

## 4. Detection semantics

Assume `M` is the maximum persisted sequence in a stream and `S` is the incoming sequence.

### 4.1 First message

When no persisted sequence exists, the message establishes the baseline. OMIP does not assume that the first captured sequence must be zero.

### 4.2 Sequence gap

```text
S > M + 1
```

Details include:

- expected sequence;
- actual sequence;
- previous maximum sequence;
- number of missing messages;
- missing range.

### 4.3 Out of order

```text
S < M
```

The maximum sequence remains unchanged. The late message is retained for forensic and replay purposes.

### 4.4 Duplicate sequence

If the incoming message has a new message ID but its sequence already exists in the same stream, it is classified as `DUPLICATE_MESSAGE` with `duplicate_kind = SEQUENCE_NUMBER`. The record is stored because it may contain different payload data. When the reused sequence is also lower than the current maximum, OMIP records a second `OUT_OF_ORDER` Integrity Event because the message violates both integrity rules.

### 4.5 Duplicate message ID

If the message ID already exists, it is classified as `DUPLICATE_MESSAGE` with `duplicate_kind = MESSAGE_ID`. The Integrity Event and Alert are persisted before the primary insert is rejected by the existing unique constraint. HTTP ingestion returns `409 Conflict`.

## 5. IntegrityEvent model

```text
integrity_event_id
 dedup_key
 stream_kind
 check_type
 severity
 vehicle_id
 sensor_id (nullable for telemetry)
 mission_id
 message_id
 sequence_no
 detected_at_utc
 description
 details_json
```

`dedup_key` prevents repeated retries of the same duplicate message from creating repeated Integrity Events.

## 6. Alert model

```text
alert_id
 active_key
 integrity_event_id
 alert_type
 severity
 status
 vehicle_id
 sensor_id
 mission_id
 title
 description
 first_detected_at_utc
 last_detected_at_utc
 occurrence_count
 acknowledged_at_utc
 acknowledged_by
 resolved_at_utc
 resolved_by
 operator_note
 metadata_json
```

### 6.1 Active-key aggregation

An active alert is aggregated by:

```text
alert_type + mission_id + stream identity
```

A partial unique SQLite index enforces one active alert per key. Repeated faults update `last_detected_at_utc` and increment `occurrence_count`.

Resolving an alert sets `active_key` to `NULL`, allowing a later recurrence to create a new Alert record.

### 6.2 States

```text
OPEN
ACKNOWLEDGED
RESOLVED
```

An acknowledged Alert remains active and continues accumulating occurrences until it is resolved.

## 7. Database additions

### 7.1 `integrity_events`

Persistent immutable detection records, indexed by Mission, Sensor, check type and detection time.

### 7.2 `alerts`

Operational records indexed by status, Mission and last-detected time. A partial unique index protects active alert aggregation.

The tables are created with `CREATE TABLE IF NOT EXISTS`, so a copied v0.3.4 database is upgraded in place when v0.4.0 starts.

## 8. API surface

```text
GET /api/v1/integrity-events
GET /api/v1/integrity-events/{integrity_event_id}
GET /api/v1/missions/{mission_id}/integrity-summary

GET /api/v1/alerts
GET /api/v1/alerts/{alert_id}
POST /api/v1/alerts/{alert_id}/acknowledge
POST /api/v1/alerts/{alert_id}/resolve
```

List endpoints support filters for Mission, Vehicle, Sensor, severity, status and event/alert type where applicable.

## 9. WebSocket updates

The existing `/ws/stream` connection adds:

```text
stream_type = integrity_event
stream_type = alert
```

The Dashboard can therefore display new faults and alert lifecycle changes without waiting for periodic refresh.

## 10. Export changes

The complete Mission ZIP now contains:

```text
mission.json
quality.json
events.json
integrity-events.json
alerts.json
telemetry.csv
telemetry.jsonl
raw-messages.csv
raw-messages.jsonl
```

## 11. Compatibility

The Telemetry, RawSensorMessage and VehicleHeartbeat acquisition contracts remain at schema version `0.3.1`. Version `0.4.0` is a platform release and does not force existing producers to change their payloads.

All v0.3.4 endpoints remain available.

## 12. Deferred v0.4 work

The following checks are intentionally deferred:

- expected sampling-rate deviation;
- timestamp regression and clock drift;
- high communication latency;
- invalid payload trend alerts;
- sensor-offline alert generation;
- MQTT disconnect alerts;
- system and database performance metrics;
- application-log persistence.
