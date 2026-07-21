# OMIP Starter v0.5.3

**Environment-Aware Motion and Obstacle Interaction**

OMIP v0.5.3 extends v0.5.1 with vehicle-specific safety envelopes, nearest-obstacle analysis, collision-risk estimates and basic obstacle-aware simulation trajectories. The existing acquisition, MQTT, integrity, monitoring, storage, Vehicle Profile and Environment Context features remain available.

> The obstacle interaction and avoidance functions are research and simulation features. They are not certified collision-avoidance or vehicle-control software.

## Main v0.5.3 capabilities

- UGV, UAV, AUV and USV safety envelopes derived from Vehicle Profile geometry.
- Static and dynamic obstacle position evaluation.
- Point, circle, sphere, box and polygon distance handling.
- Nearest-obstacle centre distance and signed clearance.
- Relative closing speed and linear time-to-collision estimate.
- Risk levels: `CLEAR`, `CAUTION`, `WARNING`, `CRITICAL`, `COLLISION`.
- Vehicle-specific basic avoidance:
  - UGV and USV: lateral avoidance;
  - UAV: primarily vertical avoidance;
  - AUV: lateral avoidance while preserving depth constraints.
- `OBSTACLE_AVOIDANCE` vehicle operating mode.
- Persistent `obstacle_interactions` records.
- Mission obstacle-interaction summaries.
- Automatic Mission Events for avoidance entry or elevated collision risk.
- Dashboard risk panel and safety-envelope overlay.
- Obstacle interaction data included in Complete Mission ZIP exports.

## Quick start on Windows

```powershell
cd E:\PHD\OMIP\v0.5.3\OMIP_Starter_v0.5.3
.\scripts\run_backend.cmd
```

Open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Press `Ctrl+F5` the first time the upgraded Dashboard is opened.

## Start from the Dashboard

In **Create Simulation** select:

1. Vehicle ID;
2. Vehicle type;
3. Vehicle Profile;
4. an obstacle-avoidance Scenario;
5. duration and transport;
6. **Start simulation**.

Recommended v0.5.3 demonstration Scenarios:

```text
ugv_active_avoidance
uav_vertical_avoidance
auv_lateral_avoidance
usv_dynamic_crossing
```

The **Obstacle Interaction and Collision Risk** panel displays the nearest obstacle, clearance, TTC, safety radius and avoidance state.

## Command-line examples

### UGV lateral avoidance

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-UGV-001 `
  --vehicle-type GROUND_VEHICLE `
  --vehicle-profile ugv-small-ackermann-v1 `
  --scenario .\scenarios\ugv_active_avoidance.json `
  --duration 45
```

### UAV vertical avoidance

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-UAV-001 `
  --vehicle-type UAV `
  --vehicle-profile uav-quadrotor-research-v1 `
  --scenario .\scenarios\uav_vertical_avoidance.json `
  --duration 35
```

### AUV lateral avoidance under current

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-AUV-001 `
  --vehicle-type AUV `
  --vehicle-profile auv-research-thruster-v1 `
  --scenario .\scenarios\auv_lateral_avoidance.json `
  --duration 45
```

### USV and moving obstacle

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-USV-001 `
  --vehicle-type USV `
  --vehicle-profile usv-small-catamaran-v1 `
  --scenario .\scenarios\usv_dynamic_crossing.json `
  --duration 45
```

## Obstacle-avoidance Scenario configuration

```json
{
  "obstacle_avoidance": {
    "enabled": true,
    "lookahead_s": 4.0,
    "clearance_margin_m": 0.8,
    "maximum_offset_m": 5.0
  }
}
```

The settings are stored in the editable Scenario and copied into the immutable Mission Environment Snapshot.

## Safety envelope

The baseline safety radius is derived from Vehicle Profile geometry:

```text
body radius + safety margin
```

For planar UGV/USV vehicles, the body radius uses the horizontal footprint diagonal. For UAV/AUV vehicles, the larger of the horizontal radius and half-height is used. The resulting envelope is deliberately conservative.

## Main v0.5.3 API

```text
GET /api/v1/missions/{mission_id}/obstacle-interactions
GET /api/v1/missions/{mission_id}/obstacle-summary
GET /api/v1/vehicles/{vehicle_id}/obstacle-status
```

Optional filters:

```text
/api/v1/missions/{mission_id}/obstacle-interactions?risk_level=WARNING&limit=500
```

## Mission export

The Complete Mission ZIP now includes:

```text
mission.json
environment.json
obstacle-interactions.json
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

## Upgrade from v0.5.1

Stop the old backend, then copy the database:

```powershell
Copy-Item `
  E:\PHD\OMIP\v0.5.1\OMIP_Starter_v0.5.1\backend\omip_v051.db `
  E:\PHD\OMIP\v0.5.3\OMIP_Starter_v0.5.3\backend\omip_v052.db
```

At startup OMIP automatically creates:

```text
obstacle_interactions
obstacle_interaction_state
```

It also adds `obstacle_avoidance_json` to the Scenario table when upgrading an existing database.

## Tests

```powershell
.\scripts\run_tests.cmd
```

The v0.5.3 test suite covers existing platform features plus safety-envelope calculation, obstacle interaction persistence, API summaries and vehicle-specific trajectory changes.

## Current boundary

v0.5.3 uses conservative geometric monitoring and a deterministic avoidance trajectory generator. It does not yet provide:

- path-search algorithms such as A*, RRT* or Hybrid A*;
- Model Predictive Control;
- certified collision avoidance;
- multi-agent negotiation;
- full constraint-violation analytics;
- inference of unknown obstacles from observed trajectories.

The next recommended release is **v0.5.3 — Constraint-Aware Mission Analytics and Interaction Visualisation**.


## v0.5.3 safety patch

Candidate avoidance paths are now checked against every active obstacle. The simulator can expand the configured offset, choose an alternate direction, or stop/hold when no safe candidate exists. See `docs/COLLISION_FREE_AVOIDANCE_SAFETY_PATCH.md`.


## v0.5.3 safety analytics

This release adds a Constraint Evaluation Engine and near-miss analytics.

New APIs:

- `GET /api/v1/missions/{mission_id}/constraint-violations`
- `GET /api/v1/missions/{mission_id}/constraint-summary`
- `GET /api/v1/vehicles/{vehicle_id}/constraint-status`
- `GET /api/v1/missions/{mission_id}/near-misses`
- `GET /api/v1/missions/{mission_id}/safety-summary`

The complete Mission package now includes `constraint-violations.json`,
`near-misses.json`, and `safety-summary.json`.
