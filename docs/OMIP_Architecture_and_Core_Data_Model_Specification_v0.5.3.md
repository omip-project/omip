# OMIP Architecture and Core Data Model Specification v0.5.3

## Scope

v0.5.3 extends environment-aware motion with constraint evaluation and
near-miss analytics.

## New entities

### constraint_violations
Stores lifecycle-based violation records with measured value, limit,
duration, sample count, maximum exceedance and position.

### near_miss_events
Stores classified NEAR_MISS, CRITICAL_NEAR_MISS and COLLISION samples linked
to obstacle interaction records.

## Runtime flow

Telemetry -> Obstacle Interaction -> Constraint Evaluation -> Near-Miss
Classification -> WebSocket/API/Export.

## Vehicle-specific evaluation

Only constraints present in the immutable Mission Environment Snapshot are
evaluated. That snapshot has already been filtered by vehicle type, vehicle
identity and required capabilities.
