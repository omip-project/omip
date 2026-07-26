<div align="center">

<img src="brand/banner/github-banner.png" width="100%">

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="brand/logo/omip-logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="brand/logo/omip-logo-light.svg">
  <img src="brand/logo/omip-logo-light.svg" width="400" alt="OMIP Logo">
</picture>

# Open Mission Intelligence Platform

### Open-source Mission Data Infrastructure for Autonomous Systems

**Build • Connect • Simulate • Observe • Replay • Analyse**
 
A vendor-neutral platform for collecting, managing, replaying and analysing mission
data from heterogeneous autonomous systems.

<br>

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?logo=eclipsemosquitto&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-success)
![Foundation](https://img.shields.io/badge/Foundation-v1.0-success)

<br>

[🚀 Quick Start](#-quick-start)
•
[🏗 Architecture](#-architecture)
•
[📚 Documentation](#-documentation)
•
[🗺 Roadmap](ROADMAP.md)
•
[🤝 Contributing](CONTRIBUTING.md)

</div>

---

> [!IMPORTANT]
>
> **OMIP is a mission data platform, not a vehicle control framework.**
>
> OMIP focuses on mission information, telemetry acquisition, environment
> modelling, replay, analytics and interoperability across heterogeneous
> autonomous vehicles.
>
> It complements existing autonomy stacks such as **ROS 2**, **PX4**,
> **Autoware**, **ArduPilot** and other domain-specific control systems.

---

# ✨ Highlights

OMIP provides a unified mission-data infrastructure designed for autonomous
systems operating across multiple domains.

- 🚀 One-command Docker deployment
- 📡 Native REST and MQTT telemetry acquisition
- 🚗 Multi-domain autonomous vehicle support
- 🌍 Environment context modelling
- 📈 Mission replay and telemetry analytics
- 📦 Dataset export for research
- 🔬 Reproducible experiments and simulation workflows
- 🧩 Extensible plugin-oriented architecture
- 🌐 Vendor-neutral mission data model
- 📚 Designed for both industry and research

---

# 🎯 Project Vision

OMIP aims to become an open and reusable mission-data platform that separates
**mission information management** from **vehicle control**.

Instead of replacing existing autonomy frameworks, OMIP provides a common layer
for storing, sharing, replaying and analysing mission information regardless of
vehicle type, communication protocol or onboard software stack.

This enables developers, researchers and organisations to build interoperable
applications across:

- Ground vehicles (UGV)
- Aerial vehicles (UAV)
- Surface vessels (USV)
- Underwater vehicles (AUV)

without redesigning mission-data infrastructure for every platform.

---

# 🌟 Why OMIP?

Modern autonomous systems often suffer from fragmented mission data.

Different robots use different:

- communication protocols
- telemetry formats
- mission representations
- environmental models
- replay tools
- storage formats

As a result, mission information is difficult to reuse across projects.

OMIP solves this problem by providing a unified platform for:

- Mission lifecycle management
- Vehicle registry
- Sensor registry
- Telemetry normalisation
- Environment representation
- Mission replay
- Safety analytics
- Dataset generation
- Research experimentation

while remaining independent of the underlying autonomy stack.

---

# 📷 Platform Preview

> 📷 Dashboard screenshots will be added in Foundation v1.x.

Future previews will include:

- Dashboard Overview
- Vehicle Management
- Mission Timeline
- Environment Viewer
- Telemetry Explorer
- Replay Engine
- Analytics Dashboard

---

# 📑 Table of Contents

- Why OMIP
- Supported Vehicle Domains
- Core Capabilities
- Platform Architecture
- Repository Structure
- Quick Start
- Documentation
- Development Status
- Roadmap
- Contributing
- Security
- Citation
- License

# 🚘 Supported Vehicle Domains

OMIP uses a vehicle-independent mission model while preserving the parameters,
constraints and environmental behaviour that differ between autonomous domains.

| Domain | OMIP Type | Current Modelling |
|---|---|---|
| Uncrewed Ground Vehicle | `GROUND_VEHICLE` | Planar motion, steering limits, footprint geometry, terrain and obstacle clearance |
| Uncrewed Aerial Vehicle | `UAV` | Three-dimensional motion, altitude limits, climb rate, wind fields and aerial constraints |
| Autonomous Underwater Vehicle | `AUV` | Depth-aware motion, underwater current fields, buoyancy-related limits and subsea constraints |
| Uncrewed Surface Vessel | `USV` | Surface navigation, channels, wind, current effects and marine operating boundaries |

Vehicle-specific behaviour is configured through **Vehicle Profiles** rather
than hard-coded into the platform.

Each profile may define:

- geometry;
- kinematics;
- dynamics;
- energy properties;
- operational limits;
- safety margins;
- available capabilities;
- supported sensors;
- environment compatibility.

This allows OMIP to maintain a common mission-data model without assuming that
all vehicles behave in the same way.

---

# 🧩 Core Capabilities

OMIP is organised around a set of reusable platform capabilities.

## Vehicle and Sensor Registry

The registry provides a consistent representation of autonomous vehicles and
their onboard or simulated sensors.

Supported functions include:

- vehicle registration;
- vehicle type classification;
- vehicle profile assignment;
- capability declaration;
- sensor registration;
- sensor sampling-rate definition;
- coordinate-frame definition;
- metadata management;
- active Mission association;
- vehicle heartbeat status.

---

## Mission Lifecycle Management

OMIP treats the Mission as the primary operational and research boundary.

A Mission contains:

- Mission identity;
- assigned vehicle;
- selected Scenario;
- Vehicle Profile version;
- effective parameter values;
- environment snapshot;
- random seed;
- sensor and telemetry data;
- events and alerts;
- integrity findings;
- obstacle interactions;
- constraint violations;
- near-miss classifications;
- exports and datasets.

The Mission lifecycle provides explicit operational states such as:

```text
CREATED
   │
   ▼
RUNNING
   │
   ├──────────────► ABORTED
   │
   ▼
COMPLETED
```

Mission transitions are recorded so that simulation runs and experiments remain
traceable and reproducible.

---

## Telemetry Acquisition

OMIP currently supports two primary acquisition paths:

```text
HTTP
MQTT
```

The platform can receive:

- raw sensor messages;
- normalised telemetry frames;
- vehicle heartbeat messages.

The acquisition layer is designed to preserve the original payload before
normalisation.

This supports:

- debugging;
- replay;
- schema migration;
- integrity analysis;
- research dataset generation;
- comparison between raw and derived data.

---

## Raw Message Preservation

Raw messages are stored with operational context, including:

- message ID;
- vehicle ID;
- sensor ID;
- Mission ID;
- sequence number;
- timestamp;
- receive time;
- transport;
- MQTT Topic;
- payload;
- quality information;
- validation state.

Preserving raw data means OMIP can reprocess old Mission data when schemas,
normalisers or analysis methods change.

---

## Telemetry Normalisation

Different sensors and vehicles may report different payload structures.

OMIP uses a normalisation layer to convert supported raw messages into a common
Telemetry model.

A normalised Telemetry frame may contain:

- three-axis position;
- three-axis velocity;
- three-axis acceleration;
- speed;
- heading;
- orientation;
- battery state;
- operating mode;
- environment vectors;
- quality indicators;
- Mission and vehicle references.

This common model allows the same Dashboard, replay and analytics functions to
work across heterogeneous vehicle types.

---

## Environment Context

OMIP models the environment as a reproducible Mission input rather than as
temporary Dashboard state.

The environment model can include:

- static obstacles;
- dynamic obstacles;
- operational constraints;
- no-go areas;
- speed limits;
- altitude limits;
- depth limits;
- wind fields;
- water-current fields;
- Scenario metadata.

When a Mission starts, OMIP can capture an immutable **Mission Environment
Snapshot** containing:

- the selected Scenario;
- Scenario version;
- obstacles;
- constraints;
- external fields;
- Vehicle Profile;
- effective parameters;
- random seed;
- snapshot hash.

This snapshot makes it possible to reconstruct the conditions under which a
Mission was executed.

---

## Simulation

The OMIP simulator generates multi-sensor Mission data using vehicle-aware
profiles and Scenario configuration.

Current simulation capabilities include:

- UGV, UAV, AUV and USV profiles;
- vehicle-specific motion;
- GNSS;
- IMU;
- battery data;
- vehicle-status messages;
- heartbeat generation;
- configurable sensor rates;
- random-seed reproducibility;
- sensor noise;
- dropouts;
- duplicate messages;
- timing faults;
- out-of-order messages;
- obstacle interaction;
- conservative avoidance behaviour;
- operational constraints;
- external wind and current fields.

The simulator supports:

```text
HTTP transport
MQTT transport
```

and can run for a fixed duration or continuously.

---

## Integrity Monitoring

OMIP includes data-integrity monitoring for identifying operational and
experimental anomalies.

Current integrity checks can include:

- duplicate message IDs;
- sequence anomalies;
- out-of-order messages;
- unexpected message rates;
- timestamp regression;
- future timestamps;
- latency;
- clock drift;
- invalid quality flags;
- missing or degraded sensor behaviour.

Integrity findings may create:

- integrity events;
- alerts;
- quality metrics;
- Mission summaries;
- sensor summaries.

---

## Obstacle Interaction and Safety Analytics

OMIP can analyse the relationship between vehicle Telemetry and Mission
environment obstacles.

Current analysis can derive:

- nearest obstacle;
- clearance distance;
- vehicle safety radius;
- risk level;
- avoidance state;
- predicted minimum clearance;
- avoidance failure;
- emergency stop;
- collision classification.

The safety layer can also produce:

- constraint violations;
- near-miss events;
- collision events;
- Mission-level safety summaries.

> [!WARNING]
>
> OMIP safety analytics are intended for research, simulation and operational
> review. They are not certified vehicle-control or collision-avoidance systems.

---

## Replay and Historical Analysis

Mission data can be reviewed after completion using:

- Telemetry history;
- raw-message history;
- Mission event timeline;
- integrity events;
- alerts;
- obstacle interactions;
- safety events;
- three-axis trajectories;
- environment snapshots;
- exports.

Replay enables developers and researchers to inspect what happened during a
Mission without rerunning the original vehicle or simulation.

---

## Export and Dataset Generation

OMIP supports multiple export paths.

Current formats include:

- CSV;
- JSONL;
- raw-message exports;
- complete Mission ZIP packages.

A complete Mission package may include:

```text
mission.json
quality.json
events.json
integrity-events.json
integrity-metrics.json
alerts.json
environment.json
obstacle-interactions.json
constraint-violations.json
near-misses.json
safety-summary.json
telemetry.csv
telemetry.jsonl
raw-messages.csv
raw-messages.jsonl
```

This makes OMIP suitable for:

- offline analysis;
- machine-learning datasets;
- reproducible experiments;
- archival;
- cross-tool data exchange.

---

# 🧭 Design Principles

OMIP follows several core design principles.

## 1. Vehicle Independence

The platform should support multiple autonomous domains without assuming a
single vehicle geometry, motion model or control system.

Vehicle-specific behaviour belongs in Vehicle Profiles, Scenario configuration
or domain adapters.

---

## 2. Raw Data First

Original messages should be preserved whenever possible.

Normalised data is useful, but raw data is required for:

- auditing;
- debugging;
- reprocessing;
- integrity analysis;
- future schema migration.

---

## 3. Reproducibility

A Mission should contain enough information to reconstruct the experiment.

This includes:

- Scenario version;
- Vehicle Profile version;
- effective parameters;
- random seed;
- environment snapshot;
- Mission data;
- event history.

---

## 4. Separation of Concerns

OMIP separates:

- vehicle control;
- data acquisition;
- mission management;
- normalisation;
- storage;
- replay;
- analytics;
- research extensions.

This prevents experimental modules from destabilising the core platform.

---

## 5. Stable Core, Experimental Extensions

Core platform contracts should remain conservative and versioned.

Research modules may evolve more quickly, but should consume platform data
through clear interfaces.

---

## 6. Observable Operation

The platform should make its own state visible.

OMIP exposes information such as:

- service health;
- MQTT connection status;
- ingestion rates;
- accepted and rejected messages;
- database performance;
- active WebSocket clients;
- system alerts;
- application logs.

---

## 7. Open and Extensible

OMIP is intended to support future integration with:

- ROS 2;
- PX4;
- ArduPilot;
- Autoware;
- MAVLink;
- custom embedded systems;
- cloud platforms;
- research pipelines.

---

# 🏗 Platform Architecture

OMIP uses a layered architecture.

OMIP v1.1 introduces dedicated repositories for vehicle profiles, scenarios,
obstacles, constraints, external fields and mission environment snapshots.

The repository layer isolates SQLite persistence from environment-domain
orchestration while preserving the existing API and runtime workflows.

```text
┌────────────────────────────────────────────────────────────┐
│                   Vehicles and Simulators                  │
│                                                            │
│     UGV          UAV          AUV          USV             │
└───────────────────────────┬────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
              HTTP                    MQTT
                │                       │
                └───────────┬───────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│                    Acquisition Layer                       │
│                                                            │
│  HTTP Endpoints • MQTT Bridge • Validation • Routing       │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│                     Raw Message Store                      │
│                                                            │
│ Payload • Topic • Transport • Timestamp • Quality          │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│                    Normalisation Layer                     │
│                                                            │
│      Raw Sensor Message → Unified Telemetry Frame          │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│                      Mission Data Core                     │
│                                                            │
│ Vehicle • Sensor • Mission • Telemetry • Event • Alert     │
└───────────────┬───────────────────┬────────────────────────┘
                │                   │
                ▼                   ▼
┌────────────────────────┐  ┌───────────────────────────────┐
│ Environment Context    │  │ Integrity and Safety         │
│                        │  │                               │
│ Obstacles              │  │ Integrity Events             │
│ Constraints            │  │ Alerts                       │
│ External Fields        │  │ Obstacle Interactions        │
│ Mission Snapshots      │  │ Near Misses                  │
└───────────────┬────────┘  └──────────────┬────────────────┘
                │                          │
                └─────────────┬────────────┘
                              ▼
┌────────────────────────────────────────────────────────────┐
│                 Dashboard and Public API                   │
│                                                            │
│ Live View • Replay • Monitoring • Configuration • Export   │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│                Datasets and Research Extensions            │
│                                                            │
│ CSV • JSONL • ZIP • SDK • Analytics • AI Modules           │
└────────────────────────────────────────────────────────────┘
```

The main layers are:

1. Vehicle and Simulator Layer
2. Acquisition Layer
3. Raw Message Storage
4. Normalisation Layer
5. Mission Data Core
6. Environment Context
7. Integrity and Safety Analytics
8. Dashboard and API
9. Export and Research Extensions

---

# 🔄 Mission Lifecycle

A Mission is the primary container for a reproducible run.

```text
REGISTER VEHICLE
        │
        ▼
REGISTER SENSORS
        │
        ▼
CREATE MISSION
        │
        ▼
CAPTURE ENVIRONMENT SNAPSHOT
        │
        ▼
START MISSION
        │
        ▼
INGEST HEARTBEATS AND SENSOR DATA
        │
        ▼
NORMALISE TELEMETRY
        │
        ▼
RUN INTEGRITY AND SAFETY ANALYSIS
        │
        ▼
COMPLETE OR ABORT MISSION
        │
        ▼
REPLAY / EXPORT / ANALYSE
```

Typical Mission states:

| State | Meaning |
|---|---|
| `CREATED` | Mission exists but has not started |
| `RUNNING` | Mission is actively receiving data |
| `COMPLETED` | Mission ended normally |
| `ABORTED` | Mission ended because of cancellation or failure |

Each Mission preserves its operational context so that the run can be reviewed
and reproduced later.

---

# 🗂 Repository Structure

The repository is organised by platform responsibility.

```text
omip/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── schemas.py
│   │   ├── mqtt_bridge.py
│   │   ├── normalizer.py
│   │   ├── integrity_service.py
│   │   ├── environment_context.py
│   │   ├── obstacle_interaction.py
│   │   ├── safety_analytics.py
│   │   ├── simulation_runs.py
│   │   ├── storage_management.py
│   │   └── static/
│   ├── requirements.txt
│   └── Dockerfile
│
├── simulator/
│   └── multi_sensor_simulator.py
│
├── vehicle_profiles/
│   └── Built-in UGV, UAV, AUV and USV profiles
│
├── scenarios/
│   └── Reproducible Mission and environment definitions
│
├── docker/
│   ├── mosquitto/
│   └── simulator/
│
├── scripts/
│   ├── Development launch scripts
│   └── Docker lifecycle scripts
│
├── docs/
│   ├── Getting Started
│   ├── Architecture
│   ├── Deployment
│   └── Project documentation
│
├── sample_data/
│   └── Example sensor and Telemetry messages
│
├── tests/
│   └── Automated test suite
│
├── brand/
│   ├── logo/
│   ├── banner/
│   └── png/
│
├── .github/
│   └── Workflows and repository templates
│
├── docker-compose.yml
├── mkdocs.yml
├── requirements-docs.txt
├── README.md
├── CONTRIBUTING.md
├── ROADMAP.md
├── SECURITY.md
├── LICENSE
└── VERSION
```

## Key directories

| Directory | Purpose |
|---|---|
| `backend/` | FastAPI service, storage, analysis and Dashboard |
| `simulator/` | Vehicle-aware multi-sensor simulation |
| `vehicle_profiles/` | Type-specific vehicle parameters |
| `scenarios/` | Environment and Mission definitions |
| `docker/` | Container deployment configuration |
| `scripts/` | Local and Docker helper commands |
| `docs/` | MkDocs source documentation |
| `tests/` | Automated verification |
| `brand/` | Official OMIP visual assets |
| `.github/` | CI, Pages and contribution templates |

---

# 🖥 Platform Screenshots

> 📷 Screenshots will be added after the Foundation v1.0 interface review.

Planned screenshots:

- Dashboard Overview
- Vehicle Registry
- Mission Detail
- Live Telemetry
- Three-Axis Trajectory
- Environment and Obstacles
- Integrity Monitoring
- Safety Analytics
- Replay
- Storage and Export

# 🚀 Quick Start

The recommended way to run OMIP is through Docker Compose.

This starts:

- OMIP Backend
- Web Dashboard
- Mosquitto MQTT Broker
- persistent SQLite storage
- export and backup directories
- optional Demo Simulator

Typical first-time setup takes approximately five minutes, depending on Docker
image download speed.

---

## Prerequisites

Install the following tools before starting.

| Requirement | Recommended Version |
|---|---|
| Git | Latest stable release |
| Docker Desktop | Latest stable release |
| Docker Compose | Included with Docker Desktop |
| Python | 3.11 or later for local development |
| Operating System | Windows 11 or Ubuntu 22.04+ |

Verify the installed tools:

```bash
git --version
docker --version
docker compose version
python --version
```

Docker Desktop must be running before OMIP containers can start.

You can verify Docker using:

```bash
docker run hello-world
```

A successful response should contain:

```text
Hello from Docker!
```

---

## Clone the Repository

```bash
git clone https://github.com/omip-project/omip.git
cd omip
```

The remaining commands should be executed from the repository root.

---

## Create the Environment File

OMIP uses a local `.env` file for deployment-specific configuration.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Windows Command Prompt:

```cmd
copy .env.example .env
```

Linux or macOS:

```bash
cp .env.example .env
```

The `.env` file is intentionally excluded from Git.

Do not commit:

```text
.env
```

Only the safe template should remain in the repository:

```text
.env.example
```

---

## Configure the HTTP Port

The default host port may be configured in `.env`.

Example:

```env
OMIP_BIND_ADDRESS=127.0.0.1
OMIP_HTTP_PORT=18080
```

The container continues to use port `8000` internally.

The host mapping becomes:

```text
127.0.0.1:18080 → container:8000
```

Using `127.0.0.1` limits access to the local computer.

For trusted LAN testing, the bind address may be changed to:

```env
OMIP_BIND_ADDRESS=0.0.0.0
```

> [!WARNING]
>
> Binding to `0.0.0.0` exposes OMIP on all host network interfaces.
> Do not use this setting on an untrusted network without authentication,
> firewall rules and TLS.

---

## Start the Core Platform

Build and start the Backend and MQTT Broker:

```bash
docker compose up -d --build
```

The `-d` option starts the services in the background.

The `--build` option ensures the local source code is included in a newly built
image.

Check the service status:

```bash
docker compose ps
```

Expected result:

```text
omip-backend    Up ... healthy
omip-mqtt       Up ... healthy
```

Container names and status formatting may vary slightly by Docker version.

---

## Open the Dashboard

Open the Dashboard using the host port configured in `.env`.

Example:

```text
http://127.0.0.1:18080
```

The Dashboard should load and display the OMIP platform state.

At this stage, no vehicle may be visible until a simulator or external vehicle
registers and begins publishing data.

---

## Open the API Documentation

FastAPI automatically exposes interactive OpenAPI documentation.

Swagger UI:

```text
http://127.0.0.1:18080/docs
```

OpenAPI schema:

```text
http://127.0.0.1:18080/openapi.json
```

The API documentation can be used to:

- inspect available endpoints;
- test requests;
- review request schemas;
- review response schemas;
- validate local deployment.

---

# 🎮 Run the Demo Mission

The Demo Simulator is defined through the Docker Compose `demo` profile.

It is not started by the normal command:

```bash
docker compose up -d
```

Start the Demo explicitly:

```bash
docker compose --profile demo up --build demo-simulator
```

Running the Demo in the foreground is recommended because the terminal displays
its activity and final summary.

The Demo Simulator will:

1. load a Vehicle Profile;
2. register a vehicle;
3. register its sensors;
4. create a Mission;
5. capture the Mission Environment Snapshot;
6. start the Mission;
7. connect to the MQTT Broker;
8. publish heartbeat messages;
9. publish raw sensor messages;
10. complete the Mission;
11. print a simulation summary.

A typical Demo configuration includes:

```text
Vehicle:   OMIP-DEMO-UGV-001
Type:      GROUND_VEHICLE
Profile:   ugv-small-ackermann-v1
Transport: MQTT
```

---

## Expected Demo Output

A successful run should show output similar to:

```text
OMIP simulator started
Vehicle registered
Sensors registered
Mission created
Mission started
Transport: MQTT
Publisher submitted messages
Publisher sent messages
Mission state requested: COMPLETE
```

The exact counts depend on:

- Mission duration;
- sensor rates;
- Scenario configuration;
- heartbeat interval;
- enabled faults.

A normal Demo Simulator container may exit with code `0` after completing the
Mission.

The Backend and MQTT containers continue running.

---

## Continuous Demo Operation

For a continuously active Demo, set the configured duration to `0` or a negative
value.

Depending on the Compose configuration, this may be controlled through `.env`:

```env
OMIP_DEMO_DURATION_S=0
```

Recreate the Demo container:

```bash
docker compose --profile demo rm -f demo-simulator
docker compose --profile demo up --build demo-simulator
```

Stop the continuous simulator using:

```text
Ctrl+C
```

The simulator requests Mission termination before closing.

---

# ✅ Verify the Deployment

After starting the Demo, verify the platform using the Dashboard and API.

Expected Dashboard state:

```text
MQTT: ON
Vehicle: ONLINE
Heartbeat: recent
Mission: RUNNING or COMPLETED
Raw messages: increasing
Telemetry: increasing
```

A completed fixed-duration Mission may display the vehicle as offline after the
heartbeat threshold expires.

This is expected.

The vehicle record and Mission history should remain stored.

---

## Verify Container Status

```bash
docker compose ps
```

Expected core services:

| Service | Expected State |
|---|---|
| `omip-backend` | Running and healthy |
| `omip-mqtt` | Running and healthy |
| `omip-demo-simulator` | Running during Demo or exited successfully afterward |

Display all containers, including stopped containers:

```bash
docker compose --profile demo ps -a
```

---

## Verify the Health Endpoint

PowerShell:

```powershell
Invoke-RestMethod `
  http://127.0.0.1:18080/api/v1/health |
  ConvertTo-Json -Depth 8
```

Typical response:

```json
{
  "status": "ok",
  "service": "omip-platform-api",
  "mqtt_enabled": true
}
```

The exact version field depends on the current OMIP release.

---

## Verify MQTT Acquisition

PowerShell:

```powershell
Invoke-RestMethod `
  http://127.0.0.1:18080/api/v1/acquisition/status |
  ConvertTo-Json -Depth 8
```

Expected MQTT state:

```json
{
  "mqtt": {
    "enabled": true,
    "started": true,
    "connected": true,
    "host": "mqtt",
    "port": 1883,
    "last_error": null
  }
}
```

The topic configuration should normally include:

```text
omip/+/sensors/+
omip/+/telemetry
omip/+/heartbeat
```

---

## Verify Vehicles

PowerShell:

```powershell
Invoke-RestMethod `
  http://127.0.0.1:18080/api/v1/vehicles |
  ConvertTo-Json -Depth 8
```

A successful Demo should include a vehicle such as:

```text
OMIP-DEMO-UGV-001
```

---

## Verify Missions

```powershell
Invoke-RestMethod `
  http://127.0.0.1:18080/api/v1/missions |
  ConvertTo-Json -Depth 8
```

The Mission should normally be:

```text
RUNNING
```

during simulation, and:

```text
COMPLETED
```

after a normal fixed-duration run.

---

## Verify Raw Messages

Use Swagger UI or the raw-message API:

```text
GET /api/v1/raw-messages
```

Raw sensor records should contain fields such as:

- vehicle ID;
- sensor ID;
- Mission ID;
- message type;
- timestamp;
- payload;
- transport;
- MQTT Topic;
- quality information.

---

## Verify Telemetry

Use:

```text
GET /api/v1/vehicles/{vehicle_id}/telemetry
```

or:

```text
GET /api/v1/missions/{mission_id}/telemetry
```

Telemetry records are created when supported raw messages are normalised.

GNSS messages normally contribute position and velocity information to the
unified Telemetry stream.

---

# 📊 Operational Health

OMIP exposes additional health and monitoring endpoints.

## Platform Health

```text
GET /api/v1/system/health
```

This endpoint may include:

- database state;
- MQTT state;
- process state;
- ingestion health;
- integrity-engine state;
- overall platform status.

---

## Runtime Metrics

```text
GET /api/v1/system/metrics
```

Runtime metrics may include:

- uptime;
- received messages;
- accepted messages;
- rejected messages;
- MQTT ingestion failures;
- HTTP ingestion failures;
- database operation timing;
- active WebSocket clients.

---

## Database Health

```text
GET /api/v1/system/database
```

Use this endpoint to verify that the SQLite database is available and writable.

---

# 📝 Logs

Logs are the first place to inspect when a container is unhealthy or a Demo
vehicle does not appear.

## Backend Logs

```bash
docker compose logs --tail=200 backend
```

Follow logs continuously:

```bash
docker compose logs -f backend
```

---

## MQTT Logs

```bash
docker compose logs --tail=200 mqtt
```

Follow Broker activity:

```bash
docker compose logs -f mqtt
```

---

## Demo Simulator Logs

```bash
docker compose --profile demo logs --tail=200 demo-simulator
```

Direct container logs:

```bash
docker logs omip-demo-simulator
```

---

## Combined Logs

```bash
docker compose logs -f backend mqtt
```

This is useful when tracing the complete path:

```text
Simulator
    ↓
Mosquitto
    ↓
MQTT Bridge
    ↓
Raw Storage
    ↓
Normaliser
    ↓
Telemetry
    ↓
Dashboard
```

---

# 🧪 Inspect MQTT Messages Directly

The Broker container includes Mosquitto tools.

Subscribe to all Topics:

```powershell
docker compose exec mqtt `
  mosquitto_sub `
  -h localhost `
  -p 1883 `
  -t "#" `
  -v
```

Start the Demo in another terminal.

Expected Topics include:

```text
omip/<vehicle-id>/heartbeat
omip/<vehicle-id>/sensors/<sensor-id>
```

This test confirms whether messages reach the Broker.

It does not by itself confirm that the Backend accepted or stored them.

---

# 💻 Local Development Mode

Docker is the recommended deployment path, but OMIP can also run directly from a
local Python environment.

## Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## Install Backend Dependencies

```bash
pip install -r backend/requirements.txt
```

---

## Start the Backend

Windows:

```powershell
.\scripts\run_backend.cmd
```

Or run Uvicorn directly:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The exact import path depends on the repository working directory and current
backend packaging structure.

---

## Start the Simulator Locally

Example:

```powershell
.\scripts\run_simulator.cmd `
  --vehicle-id OMIP-UGV-001 `
  --vehicle-type GROUND_VEHICLE `
  --vehicle-profile ugv-small-ackermann-v1 `
  --scenario .\scenarios\ugv_active_avoidance.json `
  --duration 60
```

For local MQTT operation, ensure the Broker is running and configure:

```text
--transport mqtt
--mqtt-host 127.0.0.1
--mqtt-port 1883
```

When running inside Docker, the Broker host is normally:

```text
mqtt
```

because Compose service discovery uses service names.

---

# 🛑 Stop OMIP

Stop the core services:

```bash
docker compose down
```

This removes containers and the network but keeps persistent volumes.

Stored database records and exports remain available the next time OMIP starts.

---

## Stop Without Removing Containers

```bash
docker compose stop
```

Restart:

```bash
docker compose start
```

---

# ♻️ Rebuild OMIP

Rebuild after source-code or dependency changes:

```bash
docker compose down
docker compose up -d --build
```

Force a clean Backend image build:

```bash
docker compose build --no-cache backend
docker compose up -d
```

---

# 🧹 Reset the Deployment

Remove containers and orphaned services:

```bash
docker compose down --remove-orphans
```

Rebuild:

```bash
docker compose up -d --build
```

This does not necessarily remove persistent volumes.

---

## Permanently Delete Docker Data

Use the provided reset script:

```powershell
.\scripts\docker-reset.cmd
```

The script should require explicit confirmation before deleting OMIP volumes.

A full reset may remove:

- SQLite database;
- exports;
- backups;
- runtime snapshots;
- MQTT persistence data;
- MQTT logs.

> [!CAUTION]
>
> A full reset is destructive and cannot be undone unless a backup exists.

---

# 🪟 Windows Port Troubleshooting

Windows, WSL, Hyper-V or Docker Desktop may reserve blocks of TCP ports.

Symptoms include:

```text
Ports are not available
bind: An attempt was made to access a socket in a way forbidden by its access permissions
```

Check excluded TCP port ranges using Administrator PowerShell:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

If the configured port is inside a reserved range, choose another port.

Recommended alternative:

```env
OMIP_HTTP_PORT=18080
```

Then recreate the containers:

```bash
docker compose down --remove-orphans
docker compose up -d --build
```

Avoid deleting Windows system-reserved port ranges unless you fully understand
the consequences.

---

# 🔌 MQTT Troubleshooting

## MQTT Remains in WAIT State

Check status:

```powershell
Invoke-RestMethod `
  http://127.0.0.1:18080/api/v1/acquisition/status |
  ConvertTo-Json -Depth 8
```

Confirm:

```text
enabled=true
started=true
connected=true
host=mqtt
port=1883
```

---

## Test Broker Connectivity from Backend

```powershell
docker compose exec backend python -c `
"import socket; s=socket.create_connection(('mqtt',1883),5); print(s.getpeername()); s.close()"
```

Successful output should reference the MQTT container IP and port `1883`.

---

## Check Docker Networks

```powershell
docker inspect omip-backend --format "{{json .NetworkSettings.Networks}}"
docker inspect omip-mqtt --format "{{json .NetworkSettings.Networks}}"
```

Both containers should belong to the OMIP Compose network.

---

## Paho MQTT Compatibility

OMIP requires correct handling of Paho MQTT 2.x `ReasonCode` objects.

A successful connection may report:

```text
Success
```

This must not be treated as an error.

The MQTT Bridge compatibility implementation supports:

- Paho MQTT 2.x ReasonCode objects;
- legacy integer return codes;
- connection acknowledgement timeout;
- connection failure callbacks;
- reconnect delay;
- connection and subscription logging.

---

# 🔐 Current Deployment Security Boundary

The Foundation Docker deployment is intended for:

- local development;
- trusted workstation use;
- controlled demonstrations;
- research experiments.

Current development defaults may include:

- anonymous MQTT access;
- local SQLite;
- permissive CORS;
- no production authentication;
- no TLS termination.

Before exposing OMIP to a LAN or the Internet, add:

- HTTPS;
- WSS;
- authenticated MQTT over TLS;
- MQTT Topic ACLs;
- secret management;
- restricted CORS;
- user authentication;
- role-based access;
- firewall restrictions;
- backup and recovery procedures;
- monitoring and restart policies.

---

# 📷 Deployment Screenshots

> 📷 Deployment screenshots will be added after the Foundation v1.0 release review.

Planned images:

- Docker Desktop container view
- Healthy `docker compose ps` output
- OMIP Dashboard after startup
- MQTT connected state
- Demo Mission running
- Swagger API
- Platform health Dashboard

# 📚 Documentation

OMIP documentation is maintained as Markdown source and published through
MkDocs with the Material theme.

The documentation site is intended to provide a structured path for:

- first-time users;
- contributors;
- platform developers;
- researchers;
- deployment engineers;
- integration developers.

The GitHub README provides the project overview, while the documentation website
contains detailed technical and operational guidance.

---

## Documentation Website

The public documentation site is published through GitHub Pages:

```text
https://omip-project.github.io/omip/
```

The site is generated from:

```text
mkdocs.yml
docs/
```

The MkDocs source is version-controlled together with the platform code.

This ensures that:

- documentation changes can be reviewed through Pull Requests;
- documentation evolves with the implementation;
- historical versions remain traceable;
- examples can be tested against the current release;
- deployment and API guidance stays close to the source code.

---

## Documentation Structure

The current documentation structure is organised into several areas.

```text
docs/
│
├── index.md
│
├── QUICK_START.md
├── INSTALL.md
├── TROUBLESHOOTING.md
├── FAQ.md
│
├── getting-started/
│   ├── index.md
│   ├── installation.md
│   └── First-Mission.md
│
├── architecture/
│   └── index.md
│
├── deployment/
│   ├── index.md
│   └── docker.md
│
├── development/
│   └── index.md
│
├── core-data-model.md
├── vehicle-profiles.md
├── simulator.md
├── roadmap.md
│
├── stylesheets/
│   └── extra.css
│
└── images/
    ├── architecture/
    ├── banner/
    ├── icons/
    ├── logo/
    └── screenshots/
```

---

## Documentation Hub

| Document | Purpose |
|---|---|
| [`docs/QUICK_START.md`](docs/QUICK_START.md) | Five-minute local deployment |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Full installation instructions |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Common setup and runtime issues |
| [`docs/FAQ.md`](docs/FAQ.md) | Frequently asked questions |
| [`docs/getting-started/First-Mission.md`](docs/getting-started/First-Mission.md) | First Demo Mission tutorial |
| [`docs/architecture/`](docs/architecture/) | Platform architecture |
| [`docs/deployment/`](docs/deployment/) | Docker and deployment guidance |
| [`docs/core-data-model.md`](docs/core-data-model.md) | Core domain entities and relationships |
| [`docs/vehicle-profiles.md`](docs/vehicle-profiles.md) | Vehicle type and profile configuration |
| [`docs/simulator.md`](docs/simulator.md) | Simulator usage and behaviour |
| [`ROADMAP.md`](ROADMAP.md) | Project development roadmap |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow |
| [`SECURITY.md`](SECURITY.md) | Security reporting guidance |
| [`RELEASE_NOTES_v1.0.md`](RELEASE_NOTES_v1.0.md) | Foundation release notes |

---

# 🧭 Documentation Navigation

The documentation site should guide readers from general concepts to detailed
implementation.

Recommended navigation order:

```text
Home
   │
   ▼
Getting Started
   │
   ├── Installation
   ├── Quick Start
   └── First Mission
   │
   ▼
Architecture
   │
   ├── Platform Overview
   ├── Core Data Model
   ├── Acquisition
   ├── Environment Context
   └── Integrity and Safety
   │
   ▼
Platform
   │
   ├── Vehicle Profiles
   ├── Missions
   ├── Telemetry
   ├── Simulator
   └── Replay
   │
   ▼
Deployment
   │
   ├── Docker
   ├── Configuration
   ├── Persistence
   └── Security Boundary
   │
   ▼
Development
   │
   ├── Repository Workflow
   ├── Testing
   ├── Pull Requests
   └── Releases
```

---

# 🛠 Build the Documentation Locally

OMIP documentation uses a separate Python dependency file:

```text
requirements-docs.txt
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install documentation dependencies:

```powershell
pip install -r requirements-docs.txt
```

Start the local documentation server:

```powershell
mkdocs serve -a 127.0.0.1:8001
```

Open:

```text
http://127.0.0.1:8001
```

Port `8001` is recommended when the OMIP Backend is already using another local
port.

MkDocs reloads the site automatically when Markdown files change.

---

## Validate the Documentation Build

Before committing documentation changes, run:

```powershell
mkdocs build --strict
```

A strict build should complete without:

- missing navigation pages;
- invalid Markdown extensions;
- unresolved local references;
- configuration errors;
- missing files referenced by `mkdocs.yml`.

The generated static site is written to:

```text
site/
```

The `site/` directory is generated output and normally should not be maintained
manually.

---

## Documentation Publishing

OMIP uses GitHub Actions to build and deploy documentation to GitHub Pages.

Typical workflow:

```text
Push documentation changes
        │
        ▼
GitHub Actions
        │
        ▼
Install MkDocs dependencies
        │
        ▼
Run strict documentation build
        │
        ▼
Upload Pages artifact
        │
        ▼
Deploy to GitHub Pages
```

Documentation deployment should be triggered when changes affect:

```text
docs/**
mkdocs.yml
requirements-docs.txt
.github/workflows/docs.yml
```

---

# 🔌 API Documentation

OMIP exposes REST API documentation automatically through FastAPI.

Swagger UI:

```text
http://127.0.0.1:18080/docs
```

OpenAPI schema:

```text
http://127.0.0.1:18080/openapi.json
```

The OpenAPI document is the authoritative machine-readable description of the
currently running API.

It can be used for:

- interactive endpoint testing;
- client generation;
- SDK development;
- request schema inspection;
- response schema inspection;
- API compatibility review;
- documentation generation.

---

## Main API Areas

OMIP currently exposes endpoints for areas such as:

| Area | Example Path |
|---|---|
| Health | `/api/v1/health` |
| Acquisition | `/api/v1/acquisition/status` |
| Vehicles | `/api/v1/vehicles` |
| Sensors | `/api/v1/sensors` |
| Missions | `/api/v1/missions` |
| Telemetry | `/api/v1/telemetry` |
| Raw Messages | `/api/v1/raw-messages` |
| Integrity Events | `/api/v1/integrity-events` |
| Alerts | `/api/v1/alerts` |
| Vehicle Profiles | `/api/v1/vehicle-profiles` |
| Scenarios | `/api/v1/scenarios` |
| Simulation Runs | `/api/v1/simulation-runs` |
| Storage | `/api/v1/storage/*` |
| System Health | `/api/v1/system/health` |
| System Metrics | `/api/v1/system/metrics` |
| Mission Export | `/api/v1/missions/{mission_id}/export` |

The exact endpoint set depends on the current release.

---

# 🛰 MQTT Interface

OMIP uses MQTT for low-overhead asynchronous ingestion.

Current default subscription patterns include:

```text
omip/+/sensors/+
omip/+/telemetry
omip/+/heartbeat
```

Typical published Topics:

```text
omip/<vehicle-id>/sensors/<sensor-id>
omip/<vehicle-id>/heartbeat
```

Direct normalised Telemetry publication may use:

```text
omip/<vehicle-id>/telemetry
```

---

## MQTT Message Categories

| Category | Purpose |
|---|---|
| Raw Sensor Message | Preserve and normalise sensor payloads |
| Telemetry Frame | Store already normalised vehicle state |
| Heartbeat | Update vehicle operational status |

The Backend routes MQTT messages according to Topic suffix:

```text
/heartbeat
/telemetry
other matching raw-sensor Topics
```

---

## MQTT Payload Requirements

MQTT payloads must be valid UTF-8 JSON objects.

A raw sensor message generally includes:

```json
{
  "schema_version": "0.3.1",
  "message_id": "unique-message-id",
  "vehicle_id": "OMIP-UGV-001",
  "sensor_id": "OMIP-UGV-001-GNSS-001",
  "mission_id": "MISSION-001",
  "sequence_no": 1,
  "timestamp_utc": "2026-07-23T00:00:00+00:00",
  "message_type": "GNSS",
  "payload": {},
  "quality": {
    "valid": true,
    "confidence": 0.98
  }
}
```

The exact schema is defined by the Backend Pydantic models.

---

# 👨‍💻 Developer Workflow

OMIP uses a conventional Git-based contribution workflow.

Recommended sequence:

```text
Synchronise repository
        │
        ▼
Create branch
        │
        ▼
Implement focused change
        │
        ▼
Run tests
        │
        ▼
Update documentation
        │
        ▼
Commit
        │
        ▼
Push branch
        │
        ▼
Open Pull Request
        │
        ▼
Review and merge
```

---

## Clone and Prepare

```bash
git clone https://github.com/omip-project/omip.git
cd omip
```

Create a branch before making changes:

```bash
git checkout -b feature/short-description
```

Avoid developing directly on `main`.

---

# 🌿 Branch Strategy

Recommended long-lived branches:

| Branch | Purpose |
|---|---|
| `main` | Stable, reviewed project state |
| `develop` | Optional integration branch for active development |

Recommended short-lived branches:

| Prefix | Purpose |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Internal restructuring |
| `test/` | Test improvements |
| `research/` | Experimental research modules |
| `release/` | Release preparation |

Examples:

```text
feature/environment-engine
fix/mqtt-reason-code
docs/docker-quick-start
refactor/telemetry-repository
test/mqtt-end-to-end
research/trajectory-explanation
release/foundation-v1.0
```

---

# 📝 Commit Messages

Commit messages should be concise, descriptive and scoped to the change.

Recommended format:

```text
<Area>: <imperative summary>
```

Examples:

```text
Foundation: complete Docker runtime environment
Foundation: fix Paho MQTT 2.x compatibility
Docs: add five-minute Quick Start Guide
Core: add Mission environment snapshot model
Simulator: add continuous Demo mode
Integrity: detect timestamp regression
Safety: record near-miss lifecycle
Tests: add MQTT ingestion integration test
```

Avoid vague messages such as:

```text
update
changes
fix bug
final
new version
```

---

## Commit Scope

A commit should normally represent one coherent change.

Good:

```text
Fix MQTT ReasonCode handling
```

Less desirable:

```text
Fix MQTT, change Dashboard, rewrite docs, rename files and update simulator
```

Small, focused commits are easier to:

- review;
- test;
- revert;
- understand;
- include in release notes.

---

# 🧱 Coding Standards

OMIP is currently Python-based and should follow consistent engineering
practices.

## Python Version

Target:

```text
Python 3.11 or later
```

Documentation and local tooling may use newer compatible versions.

---

## General Python Guidelines

- Use type hints for public functions and core internal interfaces.
- Prefer explicit data models over unstructured dictionaries.
- Use Pydantic models for API contracts.
- Keep transport logic separate from domain logic.
- Keep persistence logic separate from HTTP routing.
- Avoid broad `except Exception` unless failure isolation is intentional.
- Log operational failures with useful context.
- Keep blocking I/O away from the FastAPI event loop.
- Use UTC timestamps.
- Preserve message IDs and Mission context.
- Avoid hidden global mutable state where practical.

---

## Formatting

Recommended tools:

```text
Black
Ruff
isort
```

Possible commands:

```bash
black backend simulator tests
ruff check backend simulator tests
isort backend simulator tests
```

The exact tool configuration should be committed before enforcing formatting in
CI.

---

## Type Checking

Recommended tool:

```text
mypy
```

Example:

```bash
mypy backend
```

Type checking may initially be introduced incrementally because some existing
modules use dynamic payloads and SQLite row dictionaries.

---

## Naming

Recommended conventions:

| Item | Convention |
|---|---|
| Python modules | `snake_case.py` |
| Functions | `snake_case` |
| Variables | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_CASE` |
| API paths | lowercase, hyphen-separated where needed |
| Environment variables | `OMIP_UPPER_CASE` |
| Database tables | consistent plural or singular convention |
| Message IDs | globally unique strings |
| Mission IDs | stable human-readable identifiers where practical |

---

# 🧪 Testing

Automated tests are required for changes that affect platform behaviour.

The test suite is located in:

```text
tests/
```

Run all tests:

```bash
pytest
```

Run with detailed output:

```bash
pytest -v
```

Stop after the first failure:

```bash
pytest -x
```

Run a specific file:

```bash
pytest tests/test_mqtt_bridge.py
```

Run a specific test:

```bash
pytest tests/test_mqtt_bridge.py::test_name
```

---

## Recommended Test Categories

| Category | Purpose |
|---|---|
| Unit Tests | Validate isolated services and utility functions |
| Repository Tests | Validate SQLite persistence and query behaviour |
| API Tests | Validate HTTP contracts and status codes |
| MQTT Tests | Validate connection, routing and ingestion |
| Simulator Tests | Validate deterministic message generation |
| Integration Tests | Validate multi-component data flow |
| Regression Tests | Prevent reintroduction of fixed defects |
| Export Tests | Validate CSV, JSONL and ZIP output |
| Documentation Tests | Validate examples and links where practical |

---

## MQTT End-to-End Test

A high-value integration test should verify:

```text
Start Broker
    │
    ▼
Start Backend
    │
    ▼
Publish Raw Sensor Message
    │
    ▼
Backend Receives Message
    │
    ▼
Raw Message Stored
    │
    ▼
Telemetry Normalised
    │
    ▼
Vehicle Status Updated
```

This test would have detected failures such as:

- Broker connection not maintained;
- Paho ReasonCode misclassification;
- Topic mismatch;
- message validation failure;
- normalisation failure;
- database persistence failure.

---

## Deterministic Simulation Tests

Simulator tests should specify a fixed random seed.

Example:

```text
random_seed = 42
```

A deterministic test should verify:

- expected number of generated messages;
- expected sensor rates;
- stable Mission duration;
- reproducible trajectory samples;
- expected obstacle interaction;
- expected fault injection;
- no unexpected message loss.

---

# 🔍 Pull Request Requirements

Before opening a Pull Request:

- run the relevant tests;
- build the documentation;
- verify Docker deployment if runtime behaviour changed;
- update release notes when appropriate;
- update schemas and examples when public contracts changed;
- confirm no secrets or local databases are included;
- keep the change focused.

---

## Pull Request Checklist

```text
[ ] The change has a clear purpose.
[ ] Relevant tests pass.
[ ] New behaviour has tests.
[ ] Documentation is updated.
[ ] Public API changes are described.
[ ] Docker deployment still works.
[ ] MQTT ingestion still works where applicable.
[ ] No .env file is committed.
[ ] No local SQLite database is committed.
[ ] No generated exports or backups are committed.
[ ] No credentials or tokens are committed.
```

---

## Pull Request Description

A useful Pull Request description should include:

1. Problem
2. Proposed change
3. Implementation notes
4. Testing performed
5. Documentation changes
6. Compatibility considerations
7. Screenshots, when UI behaviour changes

Example:

```text
Problem:
Paho MQTT 2.x ReasonCode objects were interpreted incorrectly.

Change:
Add compatibility handling for ReasonCode.is_failure and legacy integer codes.

Testing:
- Docker Backend and Mosquitto started successfully.
- Acquisition status returned connected=true.
- Demo Mission produced raw and normalised Telemetry.
```

---

# 🔄 Continuous Integration

Recommended CI checks include:

```text
Source checkout
    │
    ▼
Install Python
    │
    ▼
Install dependencies
    │
    ├── Lint
    ├── Type check
    ├── Unit tests
    ├── Integration tests
    ├── Documentation build
    └── Docker build
```

---

## Suggested GitHub Actions Workflows

```text
.github/workflows/
├── ci.yml
├── docs.yml
├── docker.yml
├── release.yml
└── security.yml
```

| Workflow | Purpose |
|---|---|
| `ci.yml` | Linting, tests and validation |
| `docs.yml` | MkDocs build and GitHub Pages deployment |
| `docker.yml` | Container image build |
| `release.yml` | Release artifact publication |
| `security.yml` | Dependency and code scanning |

---

# 📦 Release Process

OMIP releases should be reproducible and documented.

Recommended process:

```text
Confirm roadmap milestone
        │
        ▼
Freeze release scope
        │
        ▼
Run complete tests
        │
        ▼
Run Docker end-to-end Demo
        │
        ▼
Build documentation
        │
        ▼
Update VERSION
        │
        ▼
Update CHANGELOG
        │
        ▼
Write Release Notes
        │
        ▼
Create Git Tag
        │
        ▼
Publish GitHub Release
```

---

## Versioning
**Current release candidate:** `v1.1.0-rc1`

**Latest stable release:** `v1.0.1`

Recommended semantic versioning:

```text
MAJOR.MINOR.PATCH
```

Examples:

```text
0.5.3
0.5.3.2
0.6.0
1.0.0
```

Pre-release examples:

```text
1.0.0-alpha.1
1.0.0-beta.1
1.0.0-rc.1
```

Foundation milestone tag:

```text
v1.0.0-foundation
```

This tag is descriptive but not a standard semantic-version pre-release form.

A more conventional equivalent would be:

```text
v1.0.0-foundation.1
```

or:

```text
v1.0.0-alpha.1
```

The project should choose one release convention and document it consistently.

---

## Release Checklist

```text
[ ] VERSION updated
[ ] CHANGELOG updated
[ ] Release Notes completed
[ ] Tests passed
[ ] Docker Demo passed
[ ] MQTT ingestion passed
[ ] Documentation strict build passed
[ ] GitHub Pages deployed
[ ] No local files staged
[ ] Tag created
[ ] GitHub Release published
```

---

## Create a Git Tag

Example:

```bash
git tag -a v1.0.0-foundation -m "OMIP Foundation v1.0"
git push origin v1.0.0-foundation
```

---

## Release Notes

Release notes should summarise:

- purpose of the release;
- major capabilities;
- fixed defects;
- compatibility notes;
- upgrade steps;
- known limitations;
- next milestone.

The Foundation release notes are maintained in:

```text
RELEASE_NOTES_v1.0.md
```

---

# 🗃 Files That Must Not Be Committed

Local or generated files should be excluded through `.gitignore`.

Examples:

```gitignore
.env
.venv/
site/
__pycache__/
*.pyc
*.db
*.db-shm
*.db-wal
backend/storage/
exports/
backups/
```

The exact ignore rules should reflect which sample databases or generated files
the repository intentionally includes.

Never commit:

- passwords;
- access tokens;
- cloud credentials;
- private keys;
- real vehicle credentials;
- production MQTT passwords;
- unredacted personal data;
- sensitive Mission datasets.

---

# 📷 Developer Workflow Screenshots

> 📷 Developer workflow screenshots will be added after the Foundation release.

Planned screenshots:

- GitHub Actions summary
- Documentation deployment workflow
- Pull Request checklist
- Test execution
- Docker build
- Release creation

# 📈 Development Status

OMIP is under active development.

The current platform has completed the primary Foundation work required for a
reproducible local runtime, public documentation and a working Demo workflow.

The next major stage focuses on strengthening the platform core and formalising
stable domain contracts.

---

## Current Module Status

| Module | Status | Notes |
|---|---|---|
| Repository Foundation | ✅ Complete | GitHub structure, governance and templates |
| Branding | ✅ Complete | Logo system, Banner and Social Preview |
| Documentation Website | ✅ Complete | MkDocs Material and GitHub Pages |
| Docker Runtime | ✅ Complete | Backend, Mosquitto and optional Demo profile |
| MQTT Integration | ✅ Complete | Paho MQTT 2.x compatibility included |
| Backend API | ✅ Available | FastAPI REST and WebSocket interfaces |
| Dashboard | ✅ Available | Live platform and Mission views |
| Vehicle Registry | ✅ Available | Multi-domain vehicle records |
| Sensor Registry | ✅ Available | Sensor metadata and sampling configuration |
| Mission Lifecycle | ✅ Available | Created, running, completed and aborted states |
| Raw Message Storage | ✅ Available | HTTP and MQTT acquisition |
| Telemetry Normalisation | ✅ Available | Supported sensor messages to unified Telemetry |
| Vehicle Profiles | ✅ Available | UGV, UAV, AUV and USV parameters |
| Scenario Management | ✅ Available | Environment and Mission configuration |
| Environment Snapshots | ✅ Available | Immutable Mission-specific snapshots |
| Static Obstacles | ✅ Available | Scenario and Mission context |
| Dynamic Obstacles | 🧪 Experimental | Basic velocity-aware representation |
| External Fields | ✅ Available | Wind and water-current vectors |
| Constraint Analytics | ✅ Available | Operational rule evaluation |
| Obstacle Interaction | ✅ Available | Clearance and risk analysis |
| Near-Miss Analytics | ✅ Available | Mission safety classifications |
| Integrity Monitoring | ✅ Available | Timing, sequence and quality checks |
| System Monitoring | ✅ Available | Runtime metrics, health and alerts |
| Historical Replay | ✅ Available | Mission and Telemetry review |
| Dataset Export | ✅ Available | CSV, JSONL and ZIP packages |
| Storage Maintenance | ✅ Available | Backup, retention and cleanup |
| Python SDK | 🚧 Planned | Stable public API required first |
| ROS 2 Adapter | 🗺 Planned | Future integration layer |
| MAVLink Adapter | 🗺 Planned | Future vehicle gateway |
| Multi-Vehicle Coordination | 🗺 Planned | Beyond current independent simulations |
| Research Explanation Modules | 🧪 Experimental | Kept separate from stable platform core |
| Cloud Deployment | 🗺 Planned | After secure deployment baseline |
| Production Authentication | 🗺 Planned | Not included in Foundation runtime |

---

# ✅ Foundation v1.0 Completion Matrix

The Foundation milestone establishes the repository, documentation, deployment
and operational baseline for future OMIP development.

| Foundation Area | Deliverable | Status |
|---|---|---|
| Repository | Public GitHub repository | ✅ |
| License | MIT License | ✅ |
| Governance | Contribution and security guidance | ✅ |
| Templates | Issue and Pull Request templates | ✅ |
| Branding | Official Logo system | ✅ |
| Branding | GitHub Banner | ✅ |
| Branding | Social Preview | ✅ |
| README | Professional project landing page | 🚧 Final review |
| Documentation | MkDocs source structure | ✅ |
| Documentation | GitHub Pages deployment | ✅ |
| Deployment | Docker Compose runtime | ✅ |
| Deployment | Backend container | ✅ |
| Deployment | Mosquitto container | ✅ |
| Deployment | Persistent storage | ✅ |
| Deployment | Optional Demo Simulator profile | ✅ |
| MQTT | Backend MQTT bridge | ✅ |
| MQTT | Paho MQTT 2.x compatibility | ✅ |
| Quick Start | Five-minute setup guide | ✅ |
| Installation | Full installation guide | ✅ |
| Troubleshooting | Common-issue guide | ✅ |
| Tutorial | First Mission guide | ✅ |
| Release Notes | Foundation release notes | ✅ |
| Release | Git Tag and GitHub Release | ⏳ Pending |
| Release | Final clean-machine verification | ⏳ Pending |

Foundation v1.0 is considered ready when:

```text
README review passes
        │
        ▼
Clean-machine Quick Start passes
        │
        ▼
Strict documentation build passes
        │
        ▼
Docker end-to-end Demo passes
        │
        ▼
Tag and GitHub Release are published
```

---

# 🗺 Roadmap

OMIP development is organised into staged platform milestones.

```text
Foundation v1.0
        │
        ▼
Core Platform
        │
        ▼
Environment and Constraints
        │
        ▼
Mission Intelligence
        │
        ▼
SDK and Integrations
        │
        ▼
Research Extensions
        │
        ▼
Community Edition 1.0
```

The canonical roadmap is maintained in:

[`ROADMAP.md`](ROADMAP.md)

---

## Phase 1 — Foundation

**Goal:** Establish a professional, reproducible and publicly usable project
baseline.

Primary outcomes:

- repository governance;
- branding;
- documentation website;
- Docker runtime;
- MQTT integration;
- Demo Mission;
- Quick Start;
- first release process.

Status:

```text
Substantially complete
```

---

## Phase 2 — Core Platform

**Goal:** Formalise stable public domain contracts and reduce coupling between
API routing, persistence and platform services.

Planned work includes:

- versioned Core Domain Model;
- stable Vehicle contract;
- stable Sensor contract;
- stable Mission contract;
- stable Telemetry contract;
- Event and Alert contracts;
- command and observation abstractions;
- Repository interfaces;
- service boundaries;
- schema migration strategy;
- backward-compatibility policy;
- API versioning policy.

Expected outputs:

```text
omip-core
public schemas
migration policy
compatibility guarantees
```

---

## Phase 3 — Environment and Constraint Engine

**Goal:** Expand Mission context into a richer environment model.

Planned areas:

- terrain;
- map regions;
- static obstacles;
- dynamic obstacles;
- no-go zones;
- speed zones;
- altitude limits;
- depth limits;
- communication constraints;
- GNSS availability zones;
- battery constraints;
- wind fields;
- water-current fields;
- weather context;
- environment versioning;
- environment import and export.

This phase supports richer simulation, replay and analytics.

---

## Phase 4 — Mission Intelligence

**Goal:** Improve understanding of Mission behaviour without coupling the
platform to one control method.

Planned capabilities:

- event segmentation;
- anomaly explanation;
- trajectory comparison;
- Mission-to-Mission comparison;
- cause profiles;
- operator summaries;
- configurable analytics pipelines;
- confidence reporting;
- provenance-aware explanations;
- experiment comparison.

Research functions should remain clearly labelled as:

```text
experimental
```

until their interfaces and evaluation methods stabilise.

---

## Phase 5 — SDK and Integration Layer

**Goal:** Make OMIP easier to use from other software systems.

Planned components:

- Python SDK;
- generated API client;
- MQTT helper library;
- schema package;
- ROS 2 Adapter;
- MAVLink Adapter;
- PX4 integration examples;
- ArduPilot integration examples;
- Autoware integration examples;
- file-import adapters;
- cloud-ingestion adapters.

The SDK should target stable public contracts rather than internal database
details.

---

## Phase 6 — Multi-Vehicle and Distributed Operation

**Goal:** Support more complex Mission environments and distributed platform
deployment.

Planned areas:

- concurrent multi-vehicle Missions;
- fleet-level views;
- shared environment context;
- cross-vehicle events;
- vehicle-to-vehicle interaction analysis;
- distributed ingestion;
- queue-backed processing;
- PostgreSQL;
- scalable storage;
- service separation;
- observability stack;
- secure remote deployment.

---

## Phase 7 — Community Edition 1.0

**Goal:** Publish a stable, documented and extensible public platform release.

Target characteristics:

- stable schemas;
- compatibility policy;
- automated migrations;
- production-ready authentication baseline;
- secure MQTT configuration;
- release artifacts;
- SDK;
- integration examples;
- complete user documentation;
- complete developer documentation;
- reproducible Demo datasets;
- supported upgrade path.

---

# 🔬 Research Extensions

OMIP is designed to support research without making experimental algorithms part
of the stable platform core.

Possible research areas include:

- inverse reasoning from trajectories;
- cause estimation;
- probabilistic obstacle inference;
- current and disturbance estimation;
- Mission intent inference;
- event-level causal explanation;
- natural-language Mission summaries;
- trajectory anomaly detection;
- digital-twin comparison;
- learned world models;
- representation learning;
- uncertainty-aware analytics;
- Mission planning evaluation.

Research extensions should:

- consume documented OMIP data contracts;
- record model and configuration versions;
- preserve input provenance;
- report uncertainty;
- distinguish observation from inference;
- avoid presenting experimental conclusions as certified safety decisions;
- remain replaceable without changing the platform core.

---

## Research Data Principles

Research datasets created through OMIP should record:

- Mission ID;
- vehicle type;
- Vehicle Profile;
- Scenario version;
- environment snapshot;
- random seed;
- raw messages;
- normalised Telemetry;
- derived labels;
- analysis configuration;
- software version;
- model version;
- evaluation metrics.

This allows research results to be reviewed and reproduced.

---

## Stable Core and Research Boundary

Recommended separation:

```text
OMIP Core
   │
   ├── Vehicle
   ├── Sensor
   ├── Mission
   ├── Raw Message
   ├── Telemetry
   ├── Environment
   ├── Event
   └── Export
        │
        ▼
Research Extension Interface
        │
        ├── Trajectory Analysis
        ├── Cause Inference
        ├── Explanation
        ├── Learned Models
        └── Experiment Evaluation
```

Research modules should not directly depend on private SQLite table layouts.

---

# 🤝 Community

OMIP is being developed as an open-source platform for autonomous-system
developers, researchers and educators.

Potential contributors include:

- robotics developers;
- simulation developers;
- data engineers;
- autonomous-vehicle researchers;
- maritime robotics researchers;
- aerial robotics researchers;
- software engineering students;
- documentation contributors;
- UI developers;
- test engineers;
- integration developers.

Contributions may include:

- bug fixes;
- tests;
- documentation;
- new Vehicle Profiles;
- new Scenarios;
- API improvements;
- import and export tools;
- Dashboard improvements;
- deployment improvements;
- integration adapters;
- research modules.

---

# 🤲 Contributing

Contribution guidance is maintained in:

[`CONTRIBUTING.md`](CONTRIBUTING.md)

Before contributing:

1. review the roadmap;
2. search existing issues;
3. keep the proposed change focused;
4. create a dedicated branch;
5. include tests where relevant;
6. update documentation;
7. open a clear Pull Request.

High-value early contributions include:

- additional automated tests;
- cross-platform installation validation;
- Docker improvements;
- documentation corrections;
- sample Scenarios;
- Vehicle Profiles;
- API examples;
- MQTT integration tests;
- export validation.

---

## Contribution Areas

| Area | Example Contributions |
|---|---|
| Core | Schemas, services and Repository interfaces |
| Simulator | Vehicle motion, sensors and fault injection |
| Environment | Obstacles, fields and constraints |
| Integrity | New checks and metrics |
| Safety | Additional analytical classifications |
| Dashboard | Usability and visualisation |
| Documentation | Guides, diagrams and examples |
| Deployment | Linux, LAN and cloud references |
| Testing | Unit, integration and regression coverage |
| SDK | Client libraries and examples |
| Research | Experimental modules with documented evaluation |

---

# 🧭 Governance

OMIP governance is expected to evolve with the contributor community.

The initial model is maintainer-led:

```text
Maintainers
    │
    ├── Review changes
    ├── Approve releases
    ├── Protect public contracts
    ├── Maintain roadmap
    └── Resolve contribution questions
```

As the project grows, governance may introduce:

- module maintainers;
- reviewer groups;
- release managers;
- security contacts;
- architecture decision records;
- request-for-comment processes;
- community meetings.

---

## Architecture Decisions

Significant technical decisions should eventually be documented through
Architecture Decision Records.

Suggested structure:

```text
docs/adr/
├── 0001-use-fastapi.md
├── 0002-preserve-raw-messages.md
├── 0003-mission-environment-snapshots.md
└── 0004-version-public-contracts.md
```

An ADR should normally include:

- context;
- decision;
- alternatives;
- consequences;
- status;
- date.

---

# 🆘 Support

During the Foundation stage, support is primarily provided through GitHub.

Use GitHub Issues for:

- reproducible bugs;
- feature requests;
- documentation problems;
- installation problems;
- compatibility reports.

Before opening an issue, include:

- OMIP version;
- operating system;
- Python version;
- Docker version;
- Docker Compose version;
- deployment mode;
- steps to reproduce;
- expected behaviour;
- actual behaviour;
- relevant logs.

Do not include secrets or private Mission data in public issues.

---

## Bug Report Example

```text
OMIP version:
v1.0.0-foundation

Operating system:
Windows 11

Docker version:
...

Description:
Backend MQTT status remains in WAIT.

Steps:
1. Start Docker deployment.
2. Open Dashboard.
3. Run Demo.

Expected:
MQTT connected=true.

Actual:
MQTT connected=false.

Logs:
Relevant redacted Backend and Mosquitto lines.
```

---

# 🔐 Security

Security guidance is maintained in:

[`SECURITY.md`](SECURITY.md)

Do not disclose suspected vulnerabilities in public issues.

Potentially sensitive reports include:

- authentication bypass;
- exposed credentials;
- command injection;
- path traversal;
- unsafe file handling;
- remote code execution;
- MQTT ACL bypass;
- secret leakage;
- dependency vulnerabilities with practical impact.

The Foundation runtime is intended for local development and trusted
environments.

It is not yet a hardened public Internet deployment.

---

## Security Responsibilities

Deployers are responsible for:

- restricting network exposure;
- enabling TLS;
- configuring authentication;
- protecting secrets;
- securing MQTT;
- applying updates;
- backing up data;
- reviewing logs;
- following applicable privacy obligations.

---

# 🧾 Release Notes and Changelog

Foundation release notes:

[`RELEASE_NOTES_v1.0.md`](RELEASE_NOTES_v1.0.md)

A project changelog should summarise meaningful changes by release:

```text
CHANGELOG.md
```

Recommended categories:

- Added
- Changed
- Deprecated
- Removed
- Fixed
- Security

---

# 📖 Citation

Academic citation support should be provided through:

```text
CITATION.cff
```

Until an archived release and formal citation metadata are available,
researchers may cite:

- the GitHub repository;
- the release version;
- the Git commit;
- the access date.

A future archived release may use a DOI provider such as Zenodo.

---

## Suggested Interim Citation

```text
Open Mission Intelligence Platform contributors.
Open Mission Intelligence Platform (OMIP), version <version>.
GitHub repository, <year>.
```

Replace `<version>` with the specific release or Git commit used.

---

## Reproducible Research Citation

Research using OMIP should ideally record:

- OMIP release;
- Git commit;
- exported Mission package;
- Scenario;
- Vehicle Profile;
- random seed;
- research-module version.

This is more reproducible than citing only the project homepage.

---

# ⚖️ License

OMIP Core is released under the:

[MIT License](LICENSE)

The MIT License permits:

- use;
- copying;
- modification;
- distribution;
- sublicensing;
- commercial use,

subject to the License terms and preservation of the copyright and permission
notice.

Individual datasets, third-party assets, integrations or research models may
have separate licenses.

Contributors should not add incompatible third-party material without clearly
documenting its license.

---

# 🙏 Acknowledgements

OMIP builds on the wider open-source ecosystem.

Relevant technologies and communities include:

- Python;
- FastAPI;
- Pydantic;
- SQLite;
- Docker;
- Eclipse Mosquitto;
- Paho MQTT;
- MkDocs;
- Material for MkDocs;
- GitHub Actions;
- autonomous-systems and robotics communities.

Acknowledgement does not imply affiliation or endorsement.

---

# 📷 Community and Roadmap Screenshots

> 📷 Community, roadmap and release screenshots will be added after the
> Foundation v1.0 release.

Planned images:

- GitHub project roadmap
- GitHub Release page
- Issue templates
- Pull Request workflow
- Documentation homepage
- Research export example

---

<div align="center">

# Open Mission Intelligence Platform

### Mission Data Infrastructure for Autonomous Systems

**Open • Reproducible • Vehicle-Independent • Extensible**

Built for autonomous-system development, mission analysis and robotics research.

⭐ If OMIP is useful to your work, consider starring the repository.

</div>