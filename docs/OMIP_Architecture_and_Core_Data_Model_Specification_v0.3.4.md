# OMIP Architecture and Core Data Model Specification v0.3.4

## 1. Purpose

OMIP v0.3.4 is a Dashboard reliability patch. The persistence model and acquisition contracts remain compatible with v0.3.3. The release corrects Mission-selection behaviour and separates Mission export availability from optional historical preview loading.

## 2. Corrected interaction model

The Dashboard maintains two independent states:

- `selectedVehicle`: the fleet-detail filter;
- `selectedMission`: the historical Mission being inspected.

Periodic fleet refreshes may update registry data, status and counts, but they must not discard an operator's Mission selection. Select elements are rebuilt only when their option signatures change and they are not focused.

## 3. Mission loading lifecycle

Mission selection follows these states:

```text
LIVE -> LOADING -> HISTORY
                 -> HISTORY* when one preview has warnings
                 -> ERROR for an unhandled load failure
```

A monotonically increasing load token prevents an older asynchronous request from overwriting a newer Mission selection.

## 4. Independent preview requests

The Dashboard loads three previews concurrently:

```text
GET /api/v1/missions/{mission_id}/telemetry?limit=20000
GET /api/v1/raw-messages?mission_id={mission_id}&limit=200
GET /api/v1/missions/{mission_id}/events
```

`Promise.allSettled` is used so one failed preview does not suppress successful data from the other requests.

The limits apply only to interactive previews. Export endpoints continue to produce the complete Mission files according to their server-side implementation.

## 5. Export independence

Immediately after a Mission is selected, the Dashboard configures these links:

```text
GET /api/v1/missions/{mission_id}/export?format=csv
GET /api/v1/missions/{mission_id}/export?format=jsonl
GET /api/v1/missions/{mission_id}/raw/export?format=csv
GET /api/v1/missions/{mission_id}/raw/export?format=jsonl
GET /api/v1/missions/{mission_id}/export/package
```

Historical preview failure must not disable these links.

## 6. Compatibility

No table or message-schema changes are introduced. A v0.3.3 SQLite database can be copied and used as the v0.3.4 database.

## 7. Future work

A later operational-monitoring release should add server-side pagination, background export jobs, authentication, persistent user filters and browser-level automated interaction tests.
