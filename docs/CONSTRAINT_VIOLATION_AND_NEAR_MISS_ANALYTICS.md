# OMIP v0.5.3 — Constraint Violation and Near-Miss Analytics

OMIP evaluates every normalised telemetry frame against the immutable Mission
Environment Snapshot.

Supported checks:

- SPEED_LIMIT_VIOLATION
- NO_ENTRY_ZONE_VIOLATION
- ALTITUDE_LIMIT_VIOLATION
- DEPTH_LIMIT_VIOLATION
- MISSION_BOUNDARY_EXIT
- REQUIRED_CORRIDOR_EXIT
- LOW_BATTERY_RETURN_VIOLATION
- NEAR_MISS
- CRITICAL_NEAR_MISS
- COLLISION

Constraint violations use OPEN, ONGOING and RESOLVED lifecycle states. Repeated
samples update one active record rather than creating one record per frame.

Near-miss classification uses clearance, time to collision and the
vehicle-specific safety envelope. Results are simulation and research aids,
not a certified safety controller.
