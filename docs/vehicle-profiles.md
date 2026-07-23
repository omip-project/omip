# Vehicle profiles

Vehicle profiles define parameters that differ across autonomous platforms.

Supported domains:

- `GROUND_VEHICLE`
- `UAV`
- `AUV`
- `USV`

Parameters are grouped into:

- Geometry
- Kinematics
- Dynamics
- Energy
- Operational limits
- Capabilities

A mission stores the effective parameter snapshot used for a simulation run,
rather than only the profile name.
