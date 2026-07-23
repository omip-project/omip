# Core data model

OMIP organises operational data around several primary entities.

| Entity | Purpose |
|---|---|
| Vehicle | Identity, type, capabilities, and effective parameters |
| Sensor | Source definition, sampling characteristics, and status |
| Mission | Lifecycle and reproducible experiment boundary |
| Raw message | Original sensor or vehicle payload |
| Telemetry | Normalised vehicle-state representation |
| Scenario | Editable environment and simulation template |
| Environment snapshot | Immutable mission-specific environment |
| Integrity event | Detected data-quality or timing anomaly |
| Alert | Operator-facing issue lifecycle |
| Obstacle interaction | Clearance, risk, and avoidance information |
| Constraint violation | Lifecycle-based rule violation |
| Near-miss event | Safety classification derived from interaction data |

Detailed schemas will be linked from the existing architecture specifications as
the public API is stabilised.
