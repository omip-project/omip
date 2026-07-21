# OMIP v0.5.0 Vehicle Profiles and Simulation Runs

## 1. Purpose

The vehicle-profile layer prevents OMIP from treating every autonomous platform as the same point-mass model. A UGV, UAV, AUV and USV have different geometry, motion dimensions, dynamic limits, energy models and operational constraints.

## 2. Shared configuration path

```text
Operations Console ─┐
                    ├─> SimulationRunConfig -> Simulator Worker -> Mission
Command line ───────┘
```

Both entry paths resolve the same profile and produce the same effective parameter snapshot.

## 3. Parameter precedence

```text
Vehicle-type definitions
        ↓
Vehicle Profile parameters
        ↓
Scenario motion settings
        ↓
Run parameter overrides
```

The final effective parameters are validated and persisted with the Simulation Run and Mission metadata.

## 4. Vehicle Profile structure

```json
{
  "profile_id": "auv-research-thruster-v1",
  "profile_name": "Research Thruster AUV",
  "vehicle_type": "AUV",
  "schema_version": "1.0",
  "capabilities": {
    "supports_3d_motion": true,
    "supports_station_keeping": true,
    "supports_depth_control": true
  },
  "parameters": {
    "geometry": {},
    "kinematics": {},
    "dynamics": {},
    "energy": {},
    "operational_limits": {}
  }
}
```

## 5. Simulation Run lifecycle

```text
QUEUED -> STARTING -> RUNNING -> COMPLETED
                         ├────> FAILED
                         └────> STOPPING -> ABORTED
```

The run record persists command arguments, PID, log path, exit code, effective parameters and timestamps.

## 6. Reproducibility snapshot

Each Mission metadata document includes:

- simulation run ID
- simulator version
- vehicle type
- vehicle profile ID and schema version
- capabilities
- effective parameters
- scenario ID
- random seed
- transport

This allows an experiment to be reconstructed after the Mission has completed.

## 7. Motion conventions

- `GROUND_VEHICLE`: planar `LOCAL_ENU`, Z fixed to zero.
- `USV`: water-surface motion, Z fixed to zero.
- `UAV`: positive Z represents altitude.
- `AUV`: negative Z represents depth below the local ENU origin.

These are starter motion generators, not high-fidelity dynamic models.

## 8. Local process security

The Simulation Run API launches a local Python process. It only accepts enumerated vehicle types, registered profile IDs and scenario IDs that resolve inside the project `scenarios` directory. Arbitrary executable paths are not accepted.

Before remote or multi-user deployment, add authentication, role-based authorization and per-user process quotas.
