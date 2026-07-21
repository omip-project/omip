# OMIP v0.5.2 Obstacle Interaction and Avoidance

## 1. Purpose

v0.5.2 adds a transparent baseline for measuring how a vehicle interacts with known Scenario obstacles. It connects Vehicle Profile geometry, immutable Mission environment snapshots, telemetry and Mission Events.

The implementation is designed for simulation, data collection and algorithm comparison. It is not a safety-certified controller.

## 2. Processing flow

```text
Vehicle Profile + Mission Environment Snapshot
                     |
Telemetry ---------->| Obstacle Interaction Service
                     |-- safety envelope
                     |-- nearest geometry distance
                     |-- signed clearance
                     |-- relative closing speed
                     |-- TTC estimate
                     |-- risk classification
                     v
              obstacle_interactions
                     |
          Dashboard / Events / Export
```

## 3. Risk levels

- `CLEAR`: no immediate proximity concern.
- `CAUTION`: the obstacle is inside the extended monitoring distance or TTC is below 10 seconds.
- `WARNING`: the obstacle is near the safety envelope or TTC is below 5 seconds.
- `CRITICAL`: very small clearance or TTC below 2 seconds.
- `COLLISION`: signed clearance is zero or negative.

TTC is only produced when the relative velocity is closing toward the obstacle.

## 4. Geometry support

- `POINT`: Euclidean point distance.
- `CIRCLE`: two-dimensional radial distance.
- `SPHERE`: three-dimensional radial distance.
- `BOX`: axis-aligned signed-distance approximation.
- `POLYGON`: two-dimensional edge distance and inside/outside test.

Dynamic obstacles translate their initial geometry using the configured velocity vector and elapsed Mission time.

## 5. Vehicle-specific behaviour

The simulator uses a deterministic, potential-field-inspired trajectory offset:

- UGV: lateral offset around obstacles while remaining at `z=0`.
- USV: lateral offset while remaining on the water surface.
- UAV: primarily vertical offset, followed by altitude-limit enforcement.
- AUV: lateral offset to preserve operating depth and depth constraints.

The simulation reports `OBSTACLE_AVOIDANCE` through the Vehicle Status sensor while avoidance is active.

## 6. Persistence

`obstacle_interactions` stores one nearest-obstacle assessment per normalised telemetry frame when the Mission contains obstacles.

Important fields:

```text
interaction_id
mission_id
vehicle_id
obstacle_id
telemetry_message_id
timestamp_utc
risk_level
centre_distance_m
clearance_m
time_to_collision_s
closing_speed_mps
safety_radius_m
obstacle_radius_m
avoidance_active
details_json
```

`obstacle_interaction_state` stores the previous risk and avoidance state. It is used to create Mission Events on relevant state transitions without creating an event for every telemetry sample.

## 7. APIs

```text
GET /api/v1/missions/{mission_id}/obstacle-interactions
GET /api/v1/missions/{mission_id}/obstacle-summary
GET /api/v1/vehicles/{vehicle_id}/obstacle-status
```

## 8. Dashboard

The Dashboard displays:

- current risk level;
- nearest obstacle;
- signed clearance;
- TTC;
- safety radius;
- active avoidance state;
- recent interaction samples;
- optional safety-envelope overlay on XY/XZ/YZ views.

## 9. Research limitations

The baseline assumes simplified geometry, known obstacle Ground Truth and short-horizon linear relative motion for TTC. It does not model actuator delay, uncertainty propagation, nonholonomic feasibility, fluid dynamics or obstacle intent. Those limitations should be preserved in reports and demonstrations.
