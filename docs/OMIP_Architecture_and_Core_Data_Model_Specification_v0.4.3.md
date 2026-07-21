# OMIP Architecture and Core Data Model Specification v0.4.3

**Release:** OMIP v0.4.3 — Data Lifecycle, Storage and Performance Management  
**Status:** Implemented starter platform

## 1. Purpose

v0.4.3 adds an explicit data-lifecycle layer to the OMIP acquisition and monitoring architecture. The release is designed to keep a local multi-vehicle platform usable as Mission histories and Raw Sensor datasets grow.

## 2. Architecture

```text
Vehicles and Sensors
        │
        ▼
Acquisition and Integrity Services
        │
        ▼
SQLite Operational Store
        │
        ├── Storage Summary and Pagination
        ├── Retention Preview / Manual Cleanup
        ├── Safe Mission Deletion
        ├── Background Export Jobs
        ├── Database Backups
        └── SQLite Maintenance
```

Storage management does not replace the existing repositories. It adds a lifecycle service around the same SQLite database and preserves v0.4.2 APIs.

## 3. New persistent models

### 3.1 `storage_settings`

Stores local lifecycle configuration. v0.4.3 uses the key `retention_policy` with a JSON value.

### 3.2 `export_jobs`

```text
job_id
mission_id
export_format
state
progress_percent
created_at_utc
started_at_utc
completed_at_utc
file_name
file_path
file_size_bytes
error_message
metadata_json
```

Supported states are `QUEUED`, `RUNNING`, `COMPLETED` and `FAILED`.

### 3.3 `storage_backups`

```text
backup_id
label
state
created_at_utc
completed_at_utc
file_name
file_path
file_size_bytes
sha256
error_message
metadata_json
```

Backups use the SQLite backup API rather than copying a live database file directly.

## 4. Pagination contract

Paginated endpoints return:

```json
{
  "items": [],
  "page": 1,
  "page_size": 500,
  "total_items": 0,
  "total_pages": 0
}
```

Pagination uses indexed Mission and timestamp columns. The original history endpoints remain for compatibility and small dashboard previews.

## 5. Retention safety model

- The platform stores a policy but never runs automatic cleanup.
- Preview is read-only.
- Cleanup requires the exact phrase `DELETE ELIGIBLE DATA`.
- Raw Sensor and Telemetry cleanup applies only to `COMPLETED` or `ABORTED` Missions.
- `RUNNING` and `PLANNED` Missions are excluded.
- Cleanup actions create structured Application Logs.

## 6. Mission deletion

Mission deletion is a separate operation from age-based retention. It requires:

1. Delete Preview.
2. Confirmation equal to the exact Mission ID.
3. Ordered deletion of Alerts, Integrity Events, Mission Events, Heartbeats, Raw Messages, Telemetry and the Mission record.
4. A structured audit log after completion.

## 7. Export architecture

The existing immediate export endpoints are retained. The new job model provides a persistent status record and writes completed files under the configured export directory.

```text
Create Job → QUEUED → RUNNING → File Written → COMPLETED
                                  └──────────→ FAILED
```

The complete package contains Mission metadata, quality, events, integrity data, alerts, Telemetry CSV/JSONL and Raw Message CSV/JSONL.

## 8. Backup and maintenance

Supported operations:

- SQLite `PRAGMA integrity_check`
- `ANALYZE`
- `PRAGMA wal_checkpoint(TRUNCATE)`
- `VACUUM`
- Consistent SQLite online backup with SHA-256 checksum

`VACUUM` is explicitly manual because it may lock the database and require additional free disk space.

## 9. Security boundary

v0.4.3 assumes a trusted local environment. Before remote deployment, authentication, authorization, CSRF protection, encrypted transport and operator audit identity must be added, especially for cleanup, deletion, backup and maintenance endpoints.

## 10. Future direction

The next logical release is OMIP v0.5, focused on Mission analytics, time-series charts, multi-variable comparison, event timelines and research dataset management.
