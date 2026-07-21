# OMIP Architecture and Core Data Model Specification v0.4.2

## 1. Version objective

OMIP v0.4.2 adds operational observability to the existing acquisition and data-integrity architecture. The release monitors the health of the OMIP backend, database, MQTT bridge, WebSocket layer, ingestion pipeline, integrity engine and process resources.

## 2. Logical architecture

```text
Vehicles and Sensors
       │
       ├── HTTP
       └── MQTT
              │
              ▼
      Acquisition Layer
              │
      Validation / Storage
              │
      Normalisation Layer
              │
      Data Integrity Engine
              │
              ├── Integrity Events
              └── Data Alerts

OMIP Runtime Components
       │
       ├── FastAPI backend
       ├── SQLite
       ├── MQTT bridge
       ├── WebSocket managers
       ├── Ingestion counters
       ├── Integrity engine
       └── Process resources
              │
              ▼
      System Health Service
              │
              ├── Runtime Metrics
              ├── Metric Snapshots
              ├── Application Logs
              └── Platform Alerts
```

## 3. New services

### 3.1 RuntimeMetricsService

Responsibilities:

- Maintain thread-safe counters.
- Maintain rolling timestamps for rates.
- Record database write/query latency.
- Expose process memory and CPU when `psutil` is installed.
- Generate runtime snapshots without database dependency.

### 3.2 SystemHealthService

Responsibilities:

- Query repository database health.
- Query MQTT runtime status.
- Read WebSocket connection counts.
- Read runtime counters and process metrics.
- Calculate component and overall health.
- Include fleet operational counts.

### 3.3 System monitor loop

Responsibilities:

- Run periodically during FastAPI lifespan.
- Evaluate platform conditions.
- Open/update/resolve platform alerts.
- Store metric snapshots.
- Apply retention policy.
- Publish monitoring changes over WebSocket.

## 4. New database entities

### 4.1 `application_logs`

| Field | Type | Description |
|---|---|---|
| `log_id` | TEXT PK | Generated log identifier |
| `timestamp_utc` | TEXT | UTC occurrence time |
| `level` | TEXT | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `component` | TEXT | API, DATABASE, MQTT, SYSTEM, etc. |
| `event_type` | TEXT | Stable machine-readable event name |
| `message` | TEXT | Human-readable description |
| `vehicle_id` | TEXT nullable | Optional vehicle context |
| `sensor_id` | TEXT nullable | Optional sensor context |
| `mission_id` | TEXT nullable | Optional Mission context |
| `details_json` | TEXT | Structured details |

### 4.2 `system_metric_snapshots`

| Field | Type | Description |
|---|---|---|
| `snapshot_id` | TEXT PK | Generated snapshot identifier |
| `timestamp_utc` | TEXT | Capture time |
| `overall_status` | TEXT | HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN |
| `uptime_seconds` | REAL | Backend uptime |
| `raw_rate_per_second` | REAL | One-minute raw rate |
| `telemetry_rate_per_second` | REAL | One-minute telemetry rate |
| `http_rate_per_second` | REAL | One-minute HTTP rate |
| `mqtt_rate_per_second` | REAL | One-minute MQTT rate |
| `database_write_latency_ms` | REAL nullable | Rolling average |
| `database_query_latency_ms` | REAL nullable | Rolling average |
| `websocket_clients` | INTEGER | Connected client total |
| `memory_usage_mb` | REAL nullable | Process RSS |
| `cpu_percent` | REAL nullable | Process CPU percentage |
| `open_alerts` | INTEGER | Data plus platform alerts |
| `details_json` | TEXT | Full health snapshot |

### 4.3 `platform_alerts`

| Field | Type | Description |
|---|---|---|
| `alert_id` | TEXT PK | Generated platform alert ID |
| `active_key` | TEXT unique nullable | Deduplication key for an active condition |
| `alert_type` | TEXT | Platform alert type |
| `severity` | TEXT | INFO/WARNING/CRITICAL |
| `status` | TEXT | OPEN/ACKNOWLEDGED/RESOLVED |
| `component` | TEXT | Affected OMIP component |
| `title` | TEXT | Alert title |
| `description` | TEXT | Alert description |
| `first_detected_at_utc` | TEXT | Initial detection |
| `last_detected_at_utc` | TEXT | Most recent detection |
| `occurrence_count` | INTEGER | Number of evaluations/occurrences |
| `acknowledged_at_utc` | TEXT nullable | Operator acknowledgement time |
| `acknowledged_by` | TEXT nullable | Operator identity |
| `resolved_at_utc` | TEXT nullable | Resolution time |
| `resolved_by` | TEXT nullable | Operator or system |
| `resolution_source` | TEXT nullable | MANUAL/AUTOMATIC |
| `resolution_reason` | TEXT nullable | Resolution explanation |
| `operator_note` | TEXT | Operator note |
| `metadata_json` | TEXT | Component details |

## 5. Health-state semantics

```text
HEALTHY     Component is operating within configured limits.
DEGRADED    Component is available but impaired.
UNHEALTHY   Component is unavailable or has recorded a critical failure.
UNKNOWN     Optional or insufficiently observed component.
```

MQTT disabled by operator is `UNKNOWN`. MQTT enabled but disconnected is `DEGRADED`.

## 6. API additions

```text
GET /api/v1/system/health
GET /api/v1/system/metrics
GET /api/v1/system/database
GET /api/v1/system/logs
GET /api/v1/system/logs/{log_id}
GET /api/v1/system/metrics/snapshots
GET /api/v1/system/platform-alerts
GET /api/v1/system/platform-alerts/{alert_id}
POST /api/v1/system/platform-alerts/{alert_id}/acknowledge
POST /api/v1/system/platform-alerts/{alert_id}/resolve
```

## 7. Backward compatibility

- Existing v0.4.1 API routes remain unchanged.
- Existing databases can be copied to `backend/omip_v042.db`.
- New tables and platform-alert acknowledgement columns are added automatically.
- HTTP-only operation remains supported.
- MQTT remains optional and can be controlled at runtime.

## 8. Security and deployment note

The starter platform remains a local-development system. CORS is permissive, APIs are unauthenticated and SQLite is local. Production deployment requires authentication, access control, secret management, TLS, database hardening and network policy.
