# OMIP v0.4.2 System Monitoring and Operational Health

## 1. Purpose

The operational monitoring layer determines whether OMIP itself is capable of receiving, validating, storing, processing and broadcasting vehicle data. It complements the data-integrity engine; it does not replace it.

A sensor integrity event answers questions such as:

- Did a GNSS sequence number jump?
- Is an IMU stream arriving too slowly?
- Is communication latency excessive?

A platform health result answers questions such as:

- Is SQLite available?
- Is the MQTT bridge connected?
- Are HTTP messages being rejected unusually often?
- Is the integrity engine failing?
- Is the backend process using excessive memory?

## 2. Components

The `SystemHealthService` evaluates:

| Component | Healthy condition |
|---|---|
| Backend | FastAPI application is running |
| Database | SQLite connection and `PRAGMA quick_check` succeed |
| MQTT | Connected when MQTT is enabled; disabled MQTT remains `UNKNOWN` |
| WebSocket | Connection managers are available |
| Ingestion | Rejection ratio remains below the configured threshold |
| Integrity engine | No integrity-engine failures have been recorded |
| Process | Memory remains below the configured warning threshold |

Overall status is derived as follows:

```text
Any UNHEALTHY component → UNHEALTHY
Otherwise any DEGRADED component → DEGRADED
Otherwise → HEALTHY
```

`UNKNOWN` components do not reduce the overall status. This is important for optional services such as MQTT.

## 3. Runtime metrics

`RuntimeMetricsService` maintains thread-safe in-memory counters and rolling event windows.

Rates are calculated for:

```text
10 seconds
60 seconds
300 seconds
```

Tracked values include:

- HTTP messages received
- MQTT messages received
- Raw messages received
- Telemetry frames received
- Heartbeats received
- Accepted messages
- Rejected messages
- Database writes and failures
- Database queries and failures
- Integrity-engine failures
- System-monitor failures

Process metrics use `psutil` when available. OMIP continues to run if `psutil` is unavailable, but memory and CPU fields are returned as `null`.

## 4. Metric snapshots

The background monitor runs every ten seconds by default. Each cycle:

1. Calculates system health.
2. Updates or resolves platform alerts.
3. Stores one `system_metric_snapshots` row.
4. Broadcasts the snapshot through `/ws/stream`.
5. Deletes snapshots older than the configured retention period.

Snapshots contain frequently queried scalar fields and the complete health document in `details_json`.

## 5. Application logs

Structured logs are persisted in `application_logs`.

Initial logged events include:

- Service start and stop
- MQTT message rejection
- Monitoring-cycle failure
- Platform-alert acknowledgement
- Platform-alert resolution

The logging helper is deliberately failure-tolerant: a log write failure is reported to the Python logger but does not break telemetry ingestion.

## 6. Platform alerts

Platform alerts use a separate `platform_alerts` table so infrastructure problems are not confused with vehicle/sensor integrity alerts.

Each active condition has a stable `active_key`. While the condition remains active, the same alert is updated. When the condition recovers, `active_key` is cleared and the alert is resolved. A future recurrence creates a new alert record.

Current conditions:

| Active key | Alert type | Component |
|---|---|---|
| `database-unavailable` | `DATABASE_UNAVAILABLE` | database |
| `mqtt-disconnected` | `MQTT_DISCONNECTED` | mqtt |
| `high-ingestion-failure-rate` | `HIGH_INGESTION_FAILURE_RATE` | ingestion |
| `high-memory-usage` | `HIGH_MEMORY_USAGE` | process |
| `integrity-engine-failure` | `INTEGRITY_ENGINE_FAILURE` | integrity engine |

## 7. Dashboard

The v0.4.2 Operations Console adds:

- Overall health
- Backend uptime
- Database state
- Combined raw/telemetry input rate
- WebSocket client count
- Process memory
- Platform-alert count
- Component Health table
- Platform Alert actions
- Application Log table

The system panels refresh with the existing six-second dashboard refresh and also receive platform-alert, log and metric messages over WebSocket.

## 8. Database monitoring

`GET /api/v1/system/database` returns:

- Database path and file size
- Health status
- Query response time
- Journal mode
- Per-table row counts

This endpoint runs a lightweight SQLite connection check and `PRAGMA quick_check`.

## 9. Limitations

- SQLite write latency is measured around repository write calls, not at storage-device level.
- CPU percentage is process-local and depends on `psutil` sampling behaviour.
- Runtime counters reset when the backend restarts; persisted snapshots remain.
- Platform monitoring is local to one OMIP backend instance.
- No remote notification channel is included yet.
