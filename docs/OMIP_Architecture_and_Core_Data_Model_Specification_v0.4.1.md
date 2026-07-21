# OMIP Architecture and Core Data Model Specification v0.4.1

## 1. Purpose

OMIP v0.4.1 extends the v0.4.0 Data Integrity Engine from sequence continuity into timing, communication latency and sampling-rate integrity. The release keeps the v0.3.1 producer payload contracts unchanged and adds platform-side analysis, metrics and automatic Alert recovery.

## 2. Scope

The release covers:

- persistent sequence checks from v0.4.0;
- timestamp regression and future-clock detection;
- communication-latency thresholds;
- clock/latency offset change detection;
- sampling-rate comparison against Sensor Registry metadata;
- per-sensor and per-Mission integrity metrics;
- automatic resolution of recoverable Alerts;
- Dashboard presentation and Mission export.

It does not yet cover host CPU/memory monitoring, database capacity alarms, distributed tracing, application-log search or machine-learning anomaly detection.

## 3. Processing Architecture

```text
RawSensorMessage / TelemetryFrame
              |
              v
      DataIntegrityService
       |       |       |
       |       |       +-- Sampling-rate window
       |       +---------- Timestamp / latency checks
       +------------------ Sequence checks
              |
              v
       IntegrityFinding[]
              |
              v
  SQLite Integrity Events + Alerts
              |
       +------+------+
       |             |
       v             v
  WebSocket      Metrics APIs
  Dashboard      Mission export
```

Analysis occurs before message insertion so duplicate IDs and previous stream state are visible. Valid non-duplicate messages are inserted, findings are persisted and recoverable Alerts are then evaluated for automatic recovery.

## 4. Stream Identity

Raw sensor checks are scoped by:

```text
RAW_SENSOR + mission_id + sensor_id
```

Normalised telemetry checks are scoped by:

```text
TELEMETRY + mission_id + vehicle_id
```

This prevents data from one sensor, vehicle or Mission from changing the integrity state of another stream.

## 5. Integrity Check Types

### 5.1 Sequence checks

- `SEQUENCE_GAP`
- `DUPLICATE_MESSAGE`
- `OUT_OF_ORDER`

These rules are unchanged from v0.4.0.

### 5.2 Sampling-rate checks

The Sensor Registry supplies `sampling_rate_hz`. The Data Integrity Engine calculates an observed rate from message receipt timestamps in a sliding window:

```text
actual_rate_hz = (sample_count - 1) / window_span_seconds
rate_ratio = actual_rate_hz / expected_rate_hz
```

Default decisions:

```text
ratio < 0.30  -> LOW_SAMPLING_RATE / CRITICAL
ratio < 0.70  -> LOW_SAMPLING_RATE / WARNING
ratio > 1.30  -> HIGH_SAMPLING_RATE / WARNING
```

A minimum sample count and time span are required before a rate result is evaluated. This avoids startup false positives.

### 5.3 Communication latency

Signed communication latency is calculated at ingestion:

```text
signed_latency_ms = server_now_utc - message_timestamp_utc
```

Positive latency means the message timestamp is behind the server clock.

```text
>= 500 ms   -> HIGH_LATENCY / WARNING
>= 2000 ms  -> HIGH_LATENCY / CRITICAL
```

Historical imports outside the configured real-time skew window are excluded from live latency Alerts.

### 5.4 Timestamp regression

If the incoming message timestamp is earlier than the latest timestamp previously received for the same stream, the engine creates `TIMESTAMP_REGRESSION`.

This check is independent of sequence ordering. A sequence can be valid while its clock moves backwards.

### 5.5 Future timestamp

A negative signed latency means the producer clock is ahead of the server clock.

```text
>= 2000 ms ahead   -> FUTURE_TIMESTAMP / WARNING
>= 10000 ms ahead  -> FUTURE_TIMESTAMP / CRITICAL
```

### 5.6 Clock drift

The baseline implementation compares the current signed latency with the previous stored latency for the stream:

```text
drift_ms = current_latency_ms - previous_latency_ms
```

An absolute change of at least 500 ms creates `CLOCK_DRIFT`. This is a practical local-platform heuristic, not a replacement for disciplined clock synchronisation such as NTP or PTP.

## 6. Integrity Analysis Result

The service returns an `IntegrityAnalysis` object:

```text
findings
 evaluated_recoverable_types
 active_recoverable_types
```

The evaluated set records checks that had enough context to make a healthy/fault decision. The active set records the recoverable checks currently failing. Their difference is used for automatic recovery.

## 7. Alert Recovery

Recoverable Alert types are:

- `LOW_SAMPLING_RATE`
- `HIGH_SAMPLING_RATE`
- `HIGH_LATENCY`
- `FUTURE_TIMESTAMP`
- `CLOCK_DRIFT`

When a recoverable check is explicitly evaluated and no longer active, the matching Alert is updated:

```text
status = RESOLVED
active_key = NULL
resolved_by = system
resolution_source = AUTOMATIC
resolution_reason = condition returned to healthy range
```

Historical Integrity Events remain immutable. A later recurrence creates a new active Alert because the old active key was cleared.

The following remain manual-review faults:

- `SEQUENCE_GAP`
- `DUPLICATE_MESSAGE`
- `OUT_OF_ORDER`
- `TIMESTAMP_REGRESSION`

## 8. Data Model Changes

### 8.1 Alerts table additions

```text
resolution_source TEXT
resolution_reason TEXT
```

Allowed `resolution_source` values are:

```text
MANUAL
AUTOMATIC
```

The database migration adds these columns when a copied v0.4.0 database is first opened.

### 8.2 Integrity Events

No table replacement is required. New values are stored in the existing `check_type` field and check-specific measurements remain in `details_json`.

Examples:

```json
{
  "check_type": "HIGH_LATENCY",
  "details": {
    "latency_ms": 2510.4,
    "warning_threshold_ms": 500,
    "critical_threshold_ms": 2000
  }
}
```

```json
{
  "check_type": "LOW_SAMPLING_RATE",
  "details": {
    "expected_rate_hz": 5.0,
    "actual_rate_hz": 1.25,
    "rate_ratio": 0.25,
    "window_s": 8.0,
    "sample_count": 11
  }
}
```

## 9. Metrics APIs

### 9.1 Sensor metrics

```text
GET /api/v1/sensors/{sensor_id}/integrity-metrics
GET /api/v1/sensors/{sensor_id}/integrity-metrics?mission_id={mission_id}
```

The response includes:

- expected and actual sampling rate;
- rate ratio;
- received and missing messages;
- duplicate and out-of-order counts;
- timestamp and latency event counts;
- invalid-message count;
- average, P50, P95 and maximum latency;
- health status and Alert counts.

### 9.2 Mission metrics

```text
GET /api/v1/missions/{mission_id}/integrity-metrics
```

This returns the individual sensor metrics plus a Mission summary.

## 10. Dashboard

The Operations Console adds a Sensor Integrity Metrics table for the selected historical Mission. It displays:

- health status;
- expected and actual rate;
- missing, duplicate and out-of-order counts;
- average, P95 and maximum latency.

The existing Integrity Events and Active Alerts tables continue to show live WebSocket updates.

## 11. Export

The Complete Mission ZIP contains:

```text
mission.json
quality.json
events.json
integrity-events.json
integrity-metrics.json
alerts.json
telemetry.csv
telemetry.jsonl
raw-messages.csv
raw-messages.jsonl
```

## 12. Configuration

Environment variables:

```text
OMIP_INTEGRITY_RATE_WINDOW_S
OMIP_INTEGRITY_RATE_MIN_SPAN_S
OMIP_INTEGRITY_LOW_RATE_RATIO
OMIP_INTEGRITY_CRITICAL_LOW_RATE_RATIO
OMIP_INTEGRITY_HIGH_RATE_RATIO
OMIP_INTEGRITY_WARNING_LATENCY_MS
OMIP_INTEGRITY_CRITICAL_LATENCY_MS
OMIP_INTEGRITY_FUTURE_WARNING_MS
OMIP_INTEGRITY_FUTURE_CRITICAL_MS
OMIP_INTEGRITY_CLOCK_DRIFT_MS
OMIP_INTEGRITY_REALTIME_MAX_SKEW_S
```

## 13. Compatibility

Telemetry, RawSensorMessage and VehicleHeartbeat payload schemas remain `0.3.1`. OMIP v0.4.1 is a platform release and existing v0.3.1 producers do not need to change their messages.
