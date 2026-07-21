# OMIP v0.5.1 Environment Context and Constraints

## Scenario templates and Mission snapshots

Scenario templates can be edited. Mission snapshots cannot. This rule is central to OMIP reproducibility.

When a run starts, OMIP records the Scenario version, selected Vehicle Profile, effective parameters, random seed and all environment objects applicable to that vehicle. Historical replay reads this snapshot rather than the current Scenario template.

## Creating a Scenario

Use Swagger at `/docs`, or send:

```http
POST /api/v1/scenarios
Content-Type: application/json
```

```json
{
  "scenario_id": "research-test-001",
  "name": "Research environment test",
  "coordinate_frame": "LOCAL_ENU",
  "default_duration_s": 120,
  "sensor_rates_hz": {
    "GNSS": 5,
    "IMU": 20,
    "BATTERY": 1,
    "VEHICLE_STATUS": 2
  },
  "motion": {
    "forward_speed_mps": 1.5
  },
  "obstacles": [],
  "constraints": [],
  "external_fields": []
}
```

## Adding an obstacle

```json
{
  "name": "Subsea structure",
  "obstacle_type": "UNDERWATER_STRUCTURE",
  "geometry": {
    "geometry_type": "SPHERE",
    "position": {"x_m": 30, "y_m": 5, "z_m": -20},
    "radius_m": 3
  },
  "applies_to_vehicle_types": ["AUV"]
}
```

## Adding a constraint

```json
{
  "name": "Maximum depth",
  "constraint_type": "MAXIMUM_DEPTH",
  "value": 40,
  "unit": "m",
  "severity": "MANDATORY",
  "applies_to_vehicle_types": ["AUV"],
  "required_capabilities": ["supports_depth_control"]
}
```

## Adding an external field

```json
{
  "name": "Cross current",
  "field_type": "OCEAN_CURRENT",
  "coordinate_frame": "LOCAL_ENU",
  "vector": {"x": 0.1, "y": 0.3, "z": 0, "unit": "m/s"},
  "unit": "m/s",
  "applies_to_vehicle_types": ["AUV", "USV"]
}
```

## Geometry

### Point

```json
{"geometry_type": "POINT", "position": {"x_m": 10, "y_m": 2, "z_m": 0}}
```

### Circle or sphere

```json
{
  "geometry_type": "CIRCLE",
  "position": {"x_m": 20, "y_m": 5, "z_m": 0},
  "radius_m": 4
}
```

### Box

```json
{
  "geometry_type": "BOX",
  "position": {"x_m": 25, "y_m": 0, "z_m": 2},
  "length_m": 8,
  "width_m": 4,
  "height_m": 4
}
```

### Polygon

```json
{
  "geometry_type": "POLYGON",
  "points": [
    {"x_m": 0, "y_m": 0, "z_m": 0},
    {"x_m": 40, "y_m": 0, "z_m": 0},
    {"x_m": 40, "y_m": 20, "z_m": 0},
    {"x_m": 0, "y_m": 20, "z_m": 0}
  ]
}
```

## Running the examples

Use the browser or one of the Scenario files:

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-AUV-001 `
  --vehicle-type AUV `
  --vehicle-profile auv-research-thruster-v1 `
  --scenario .\scenarios\auv_current_depth.json `
  --duration 120
```

## Visualisation

The Trajectory panel supports:

- XY, XZ and YZ views;
- obstacle layer;
- constraint layer;
- external field layer;
- historical Mission environment snapshots.

For a ground vehicle, XY is normally the most useful view. UAV and AUV experiments should also be reviewed in XZ and YZ.

## Research use

The environment snapshot is Ground Truth. A later OMIP inference module can hide some or all of this Ground Truth and compare inferred obstacles or external causes against the stored snapshot.
