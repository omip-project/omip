# OMIP Architecture and Core Data Model Specification v0.5.1

## 1. Purpose

OMIP v0.5.1 introduces a formal Environment Context Layer above the acquisition, integrity, monitoring, storage and vehicle-profile layers established in earlier releases.

The release separates two concepts:

- **Scenario Template** — an editable environment definition used to prepare future runs;
- **Mission Environment Snapshot** — an immutable record of the exact environment applicable to one vehicle during one Mission.

This separation preserves experimental reproducibility. A Scenario can evolve without changing the meaning of historical telemetry.

## 2. Architecture

```text
Operations Console / REST API / Scenario JSON
                    │
                    ▼
          Environment Context Service
       ┌────────────┼──────────────┐
       ▼            ▼              ▼
   Obstacles    Constraints    External Fields
       └────────────┬──────────────┘
                    │ applicability filter
                    ▼
         Mission Environment Snapshot
                    │
                    ├── Simulator Worker
                    ├── Trajectory Visualisation
                    ├── Historical Replay
                    └── Mission Export
```

The Environment Context Service uses the same SQLite database as the rest of OMIP. It writes canonical Scenario JSON files so the local Simulator Worker and command-line workflow use the same representation as the browser and REST API.

## 3. Coordinate conventions

The default coordinate frame is `LOCAL_ENU`:

- X: East or forward reference direction;
- Y: North or lateral reference direction;
- Z: Up;
- AUV depth is represented by negative Z.

`WGS84` remains available for future geospatial integration. v0.5.1 visualisation is primarily local-coordinate based.

## 4. Scenario Template

A Scenario contains:

```text
scenario_id
name
description
coordinate_frame
origin
default_duration_s
sensor_rates_hz
motion
quality
faults
obstacles
constraints
external_fields
metadata
enabled
version
```

Every edit increments `version`. The version is copied to each Mission Environment Snapshot.

## 5. Obstacle model

Supported obstacle types:

```text
STATIC_OBSTACLE
DYNAMIC_OBSTACLE
UNKNOWN_OBJECT
TERRAIN
BUILDING
VESSEL
UNDERWATER_STRUCTURE
```

Supported geometry types:

```text
POINT
CIRCLE
SPHERE
BOX
POLYGON
```

Core fields:

```text
obstacle_id
scenario_id
name
obstacle_type
geometry
coordinate_frame
source
confidence
velocity
heading_deg
valid_from_utc
valid_to_utc
applicability
metadata
```

Dynamic obstacles can carry velocity and heading. Predicted dynamic paths are not yet generated in v0.5.1.

## 6. Constraint model

Supported constraint types:

```text
SPEED_LIMIT
NO_ENTRY_ZONE
MAXIMUM_ALTITUDE
MINIMUM_ALTITUDE
MAXIMUM_DEPTH
MINIMUM_DEPTH
MISSION_BOUNDARY
REQUIRED_CORRIDOR
CHECKPOINT
BATTERY_RETURN_THRESHOLD
COMMUNICATION_REQUIRED_ZONE
```

A constraint may be global or associated with geometry. Severity is one of:

```text
ADVISORY
RECOMMENDED
MANDATORY
```

The v0.5.1 simulator applies basic global speed limits and altitude/depth bounds. Remaining constraint-violation analytics are planned for v0.6.

## 7. External Field model

Supported field types:

```text
WIND
OCEAN_CURRENT
WATER_CURRENT
ROAD_SLOPE
SURFACE_FRICTION
TERRAIN_ELEVATION
COMMUNICATION_QUALITY
GNSS_QUALITY
```

A vector field uses:

```json
{
  "x": 0.2,
  "y": -0.1,
  "z": 0.0,
  "unit": "m/s"
}
```

A field can be global or restricted to geometry. Vector wind and current fields add drift to simulated position and velocity.

## 8. Applicability model

Each environment item can specify:

```text
applies_to_vehicle_types
applies_to_vehicle_ids
required_capabilities
```

Evaluation rules:

1. an empty vehicle-type list means all types;
2. an empty Vehicle ID list means all vehicles;
3. every required capability must be true;
4. all non-empty conditions must pass.

The filter runs before snapshot creation, so irrelevant objects do not appear in a vehicle's Mission environment.

## 9. Mission Environment Snapshot

The snapshot stores:

```text
mission_id
scenario_id
scenario_version
vehicle_id
vehicle_type
vehicle_profile_id
vehicle_capabilities
effective_vehicle_parameters
random_seed
filtered obstacles
filtered constraints
filtered external fields
snapshot_created_at_utc
sha256
```

The SHA-256 checksum is calculated from the canonical JSON payload before the checksum field is added. It allows later verification that the snapshot has not changed.

## 10. Database model

### scenarios

Stores editable Scenario metadata and motion/fault configuration.

### obstacles

Stores Scenario obstacle records and geometry JSON.

### environment_constraints

Stores operational and spatial rules.

### external_fields

Stores vector or scalar environmental effects.

### mission_environment_snapshots

Stores one immutable snapshot per Mission.

Foreign-key cascades remove the snapshot when a Mission is deliberately deleted through storage management.

## 11. API surface

Scenario APIs:

```text
GET    /api/v1/scenarios
POST   /api/v1/scenarios
GET    /api/v1/scenarios/{scenario_id}
PUT    /api/v1/scenarios/{scenario_id}
DELETE /api/v1/scenarios/{scenario_id}
```

Environment object APIs:

```text
POST   /api/v1/scenarios/{scenario_id}/obstacles
PUT    /api/v1/obstacles/{obstacle_id}
DELETE /api/v1/obstacles/{obstacle_id}

POST   /api/v1/scenarios/{scenario_id}/constraints
PUT    /api/v1/constraints/{constraint_id}
DELETE /api/v1/constraints/{constraint_id}

POST   /api/v1/scenarios/{scenario_id}/external-fields
PUT    /api/v1/external-fields/{field_id}
DELETE /api/v1/external-fields/{field_id}
```

Mission snapshot APIs:

```text
GET  /api/v1/missions/{mission_id}/environment
POST /api/v1/missions/{mission_id}/environment
```

The POST operation supports direct command-line Simulator runs. It is idempotent after a snapshot has already been captured.

## 12. User interface

The Operations Console provides:

- Scenario selection;
- obstacle, constraint and field summaries;
- a compact Add Environment Object form;
- layer toggles;
- XY, XZ and YZ projection;
- obstacle geometry overlays;
- constraint regions;
- vector-field arrows;
- automatic switch to Mission snapshots during replay.

## 13. Simulation Run integration

Browser-created runs follow this sequence:

```text
validate Vehicle Profile
→ validate Scenario
→ resolve effective vehicle parameters
→ generate Mission ID
→ create PLANNED Mission
→ filter Scenario environment
→ store Mission Environment Snapshot
→ write immutable worker Scenario file
→ create Simulation Run record
→ launch Simulator Worker
```

Direct CLI runs create the Mission through the existing API and then capture the same environment representation through the Mission environment POST endpoint.

## 14. Export

Both synchronous and background Mission packages include `environment.json`. Legacy Missions without a snapshot export an empty environment object.

## 15. Compatibility and migration

The v0.5.1 schema is additive. Copying a v0.5.0 database to `backend/omip_v051.db` preserves all prior records. New tables are created automatically.

Existing Scenario JSON files are seeded into the Scenario catalogue the first time the new database starts. Subsequent database restarts preserve the stored Scenario version rather than incrementing it unnecessarily.

## 16. Known limitations

- obstacles do not yet alter the trajectory through avoidance behaviour;
- polygon creation is available through API/JSON rather than the compact Dashboard form;
- spatial speed-zone integration is basic;
- dynamic obstacle prediction is not implemented;
- no automatic collision or constraint-violation events are generated.

These are planned for v0.5.2 and v0.6.
