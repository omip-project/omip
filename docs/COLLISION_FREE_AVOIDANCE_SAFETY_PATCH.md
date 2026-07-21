# OMIP v0.5.2.1 Collision-Free Avoidance Safety Patch

This patch replaces the single fixed-offset response with candidate-path validation. The simulator evaluates vehicle-specific avoidance directions, automatically expands the preferred offset within a hard limit, validates each candidate against all active obstacles, and uses a safe stop or hold-position fallback when no collision-free candidate exists.

## New scenario settings

- `automatic_offset_expansion`: permits the simulator to exceed the preferred offset when required.
- `hard_offset_limit_m`: absolute maximum candidate displacement.
- `lookahead_s`: obstacle influence horizon.
- `clearance_margin_m`: minimum clearance outside the vehicle and obstacle safety envelopes.

## New interaction fields

- `avoidance_failed`
- `emergency_stop`
- `fallback_action`
- `avoidance_direction`
- `predicted_minimum_clearance_m`
- `required_clearance_m`

UGV and USV fall back to `EMERGENCY_STOP`. UAV and AUV fall back to `HOLD_POSITION`. This remains a research simulator and is not a certified real-vehicle safety controller.
