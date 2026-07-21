# OMIP Architecture and Core Data Model Specification v0.3.3

## 1. Purpose

OMIP v0.3.3 is a corrective release for the v0.3 acquisition platform. It closes two operator-facing gaps: the Dashboard did not provide a clear export workflow, and trajectory visualization ignored the stored Z coordinate.

## 2. Compatibility

No database table or wire-schema migration is introduced. Existing v0.3.1 and v0.3.2 vehicle, sensor, Mission, heartbeat, raw message and telemetry records remain compatible.

## 3. Export architecture

The export flow is:

```text
Dashboard Mission selection
          |
          v
Mission Export API
          |
          +-- Normalised telemetry CSV/JSONL
          +-- Raw sensor CSV/JSONL
          +-- Complete Mission ZIP
```

The complete ZIP contains Mission metadata, quality summary, event annotations, normalized telemetry and raw sensor messages. Each file is generated from the selected Mission's stored records, not from the limited browser preview.

## 4. Export API

```text
GET /api/v1/missions/{mission_id}/export?format=csv
GET /api/v1/missions/{mission_id}/export?format=jsonl
GET /api/v1/missions/{mission_id}/raw/export?format=csv
GET /api/v1/missions/{mission_id}/raw/export?format=jsonl
GET /api/v1/missions/{mission_id}/export/package
```

The package endpoint returns `application/zip` with a `Content-Disposition` attachment filename derived from the Mission ID.

## 5. Package contents

```text
mission.json           Mission registry record and lifecycle state
quality.json           Mission data-quality summary
events.json            Mission event annotations
telemetry.csv          Flattened normalized telemetry
telemetry.jsonl        Full nested normalized telemetry
raw-messages.csv       Flattened raw-message metadata and payload JSON
raw-messages.jsonl     Full nested raw sensor messages
```

## 6. Three-axis trajectory model

Trajectory points are retained in the browser as:

```json
{
  "x": 0.0,
  "y": 0.0,
  "z": 0.0
}
```

The two-dimensional Canvas supports three projections:

```text
XY: horizontal X, vertical Y
XZ: horizontal X, vertical Z
YZ: horizontal Y, vertical Z
```

This preserves a lightweight frontend while allowing operators to inspect elevation or depth changes without adding a three-dimensional rendering dependency.

## 7. Operational behavior

Export controls remain disabled until a Mission is selected. Switching back to Live stream disables the controls, preventing accidental requests without a Mission context.

## 8. Security and scaling limits

v0.3.3 export endpoints are intended for local development and trusted networks. They have no authentication. Export generation currently builds files in memory and is suitable for development-size Mission datasets. A later release should implement authenticated access, streaming export, pagination-independent background jobs and retention policies.
