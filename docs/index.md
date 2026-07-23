# Open Mission Intelligence Platform

**Mission Data Infrastructure for Heterogeneous Autonomous Vehicles**

OMIP is an open-source platform for mission management, telemetry integration,
environmental context modelling, replay, integrity monitoring, safety analytics,
and research across heterogeneous autonomous vehicles.

<div class="grid cards" markdown>

-   :material-rocket-launch-outline:{ .lg .middle } **Get started**

    ---

    Install OMIP and run the local development environment.

    [:octicons-arrow-right-24: Getting started](getting-started/index.md)

-   :material-sitemap-outline:{ .lg .middle } **Architecture**

    ---

    Understand the main components, data flow, and platform boundaries.

    [:octicons-arrow-right-24: Architecture](architecture/index.md)

-   :material-car-connected:{ .lg .middle } **Vehicle profiles**

    ---

    Configure UGV, UAV, AUV, and USV capabilities and parameters.

    [:octicons-arrow-right-24: Vehicle profiles](vehicle-profiles.md)

-   :material-docker:{ .lg .middle } **Deployment**

    ---

    Prepare OMIP for local Docker and server deployment.

    [:octicons-arrow-right-24: Deployment](deployment/index.md)

</div>

## What OMIP provides

- Vehicle and sensor registries
- Mission lifecycle management
- HTTP and MQTT acquisition
- Raw-message preservation and normalised telemetry
- Vehicle-specific profiles and simulation
- Obstacles, constraints, wind, and current fields
- Mission environment snapshots
- Integrity monitoring and operational alerts
- Obstacle interaction and safety analytics
- Historical replay and complete mission exports

!!! warning "Research and simulation platform"
    OMIP's avoidance, integrity, and safety functions are research and simulation
    tools. They are not certified vehicle-control or collision-avoidance systems.
