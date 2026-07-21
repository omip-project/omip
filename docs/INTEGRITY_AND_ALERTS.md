# OMIP Integrity Events and Alerts

OMIP v0.4.2 evaluates each Raw Sensor and normalised Telemetry stream independently.

## Integrity checks

```text
SEQUENCE_GAP
DUPLICATE_MESSAGE
OUT_OF_ORDER
LOW_SAMPLING_RATE
HIGH_SAMPLING_RATE
HIGH_LATENCY
TIMESTAMP_REGRESSION
FUTURE_TIMESTAMP
CLOCK_DRIFT
```

Integrity Events are immutable records of detected conditions. Alerts are operational records that aggregate repeated faults for the same Mission and stream.

## Alert lifecycle

```text
OPEN -> ACKNOWLEDGED -> RESOLVED
OPEN ----------------> RESOLVED
```

Manual resolution records `resolution_source = MANUAL`.

Rate, latency, future-timestamp and clock-drift Alerts may be resolved automatically after the stream is explicitly evaluated within a healthy window. Automatic resolution records:

```text
resolved_by = system
resolution_source = AUTOMATIC
resolution_reason = condition returned to the configured healthy range
```

Sequence and timestamp-regression faults remain available for manual review because the fault already occurred even when later messages are healthy.

## Main APIs

```text
GET /api/v1/integrity-events
GET /api/v1/alerts
GET /api/v1/missions/{mission_id}/integrity-summary
GET /api/v1/missions/{mission_id}/integrity-metrics
GET /api/v1/sensors/{sensor_id}/integrity-metrics
POST /api/v1/alerts/{alert_id}/acknowledge
POST /api/v1/alerts/{alert_id}/resolve
```
