# OMIP Architecture and Core Data Model Specification v0.5.2

## 1. Release objective

OMIP v0.5.2 introduces the Obstacle Interaction Layer between normalised telemetry and Mission analytics. It uses known Environment Context and vehicle-specific parameters to estimate clearance, collision risk and avoidance activity.

## 2. Architecture

```text
Scenario Template
  |-- Obstacles
  |-- Constraints
  |-- External Fields
  |-- Avoidance Settings
          |
Vehicle Profile + Simulation Run
          |
Mission Environment Snapshot
          |
Vehicle-specific Simulator ---- Raw Sensors ---- Normalizer ---- Telemetry
          |                                                |
          |                                        Obstacle Interaction Service
          |                                                |
          +---- obstacle-aware trajectory                  +-- Interaction records
                                                           +-- Mission Events
                                                           +-- WebSocket updates
                                                           +-- Summary and export
```

## 3. Safety envelope

The effective safety radius is calculated from Vehicle Profile geometry and safety margin. Planar vehicles use the horizontal footprint. Three-dimensional vehicles also consider height.

The initial implementation uses a circular or spherical conservative envelope. Future versions may use oriented bounding boxes, swept volumes and uncertainty envelopes.

## 4. Interaction record

```json
{
  "interaction_id": "INTERACTION-...",
  "mission_id": "MISSION-001",
  "vehicle_id": "OMIP-UGV-001",
  "obstacle_id": "OBS-001",
  "risk_level": "WARNING",
  "centre_distance_m": 5.2,
  "clearance_m": 1.1,
  "time_to_collision_s": 3.4,
  "closing_speed_mps": 1.2,
  "safety_radius_m": 1.27,
  "obstacle_radius_m": 2.5,
  "avoidance_active": true
}
```

## 5. Database additions

### obstacle_interactions

Persistent per-telemetry nearest-obstacle assessments.

### obstacle_interaction_state

Last risk and avoidance state for each Mission/Obstacle pair. Supports transition detection and Mission Event creation.

### scenarios.obstacle_avoidance_json

Stores Scenario-level lookahead, margin and maximum avoidance offset settings.

## 6. APIs

```text
GET /api/v1/missions/{mission_id}/obstacle-interactions
GET /api/v1/missions/{mission_id}/obstacle-summary
GET /api/v1/vehicles/{vehicle_id}/obstacle-status
```

## 7. Simulation behaviour

v0.5.2 provides deterministic vehicle-type-specific avoidance intended to generate useful research trajectories and labelled interaction data. It is not a general path planner.

## 8. Mission Event integration

The service creates:

```text
OBSTACLE_AVOIDANCE
COLLISION_RISK
```

when the Mission enters an avoidance state or elevated risk state. Event metadata references the obstacle and interaction record.

## 9. Export

`obstacle-interactions.json` is included in both immediate Complete Mission ZIP exports and background package exports.

## 10. Compatibility

The schema is additive. A v0.5.1 database can be copied to `backend/omip_v052.db`. New tables and the new Scenario column are created automatically.

## 11. Safety statement

All v0.5.2 collision-risk and avoidance outputs are experimental. They must not be used as the only control or safety mechanism for a physical vehicle.
