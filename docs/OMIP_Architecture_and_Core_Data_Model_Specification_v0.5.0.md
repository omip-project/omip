# OMIP Architecture and Core Data Model Specification v0.5.0

**Release:** Vehicle Profiles and Simulation Run Management

## Architecture extension

```text
Vehicle Type Catalogue
        │
Vehicle Profile Registry
        │
Simulation Run Configuration
        │
Simulation Run Manager
        │
Type-aware Simulator Worker
        │
Mission + Sensor Streams + Configuration Snapshot
```

## New tables

### vehicle_parameter_definitions

Defines allowed parameter paths, data types, units, ranges and required fields for each concrete vehicle type.

### vehicle_profiles

Stores versioned parameter and capability sets. Built-in profiles are protected from deletion.

### simulation_runs

Stores the operational lifecycle and complete resolved configuration of each simulator worker.

## Vehicle extension

The `vehicles` table now supports:

```text
vehicle_profile_id
capabilities_json
parameters_json
```

These fields represent the currently assigned profile snapshot. Historical Missions independently retain their own effective snapshot.

## Built-in types

```text
GROUND_VEHICLE
UAV
AUV
USV
```

Legacy `SIMULATED` and `OTHER` values remain accepted by the registry for backward compatibility, but a concrete type is required for a new Vehicle Profile.

## Compatibility

The v0.5.0 schema is additive. A copied v0.4.3 SQLite database is migrated automatically during repository initialisation.

## Next architecture layer

The next release should introduce an Environment Context Layer containing obstacles, external fields and spatial or operational constraints. Those objects will refer to the capabilities, geometry and safety envelope established by v0.5.0.
