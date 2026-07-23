# Docker deployment

OMIP Foundation Deployment v0.1 provides a reproducible local deployment with
FastAPI, the Dashboard, SQLite persistence, Mosquitto MQTT, and an optional demo
simulator.

## Requirements

- Docker Desktop on Windows or macOS, or Docker Engine on Linux
- Docker Compose v2
- At least 2 GB of available memory

## Start OMIP

From the repository root:

```powershell
copy .env.example .env
docker compose up -d --build
```

On Windows, the helper script performs the same operation:

```powershell
.\scripts\docker-up.cmd
```

Open:

- Dashboard: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`
- Health endpoint: `http://127.0.0.1:8000/api/v1/health`

## Start the demo mission

```powershell
docker compose --profile demo up -d --build
```

or:

```powershell
.\scripts\docker-demo.cmd
```

The demo simulator runs a finite mission and then exits normally. The Backend
and MQTT services remain active.

## Check status and logs

```powershell
docker compose ps
docker compose logs -f --tail=200
```

Windows helpers:

```powershell
.\scripts\docker-status.cmd
.\scripts\docker-logs.cmd
```

## Stop services

```powershell
docker compose down
```

Named volumes are preserved, so the database and exported files remain
available after the containers stop.

## Persistent volumes

| Volume | Purpose |
|---|---|
| `omip-database` | SQLite database |
| `omip-exports` | Mission exports |
| `omip-backups` | Database backups |
| `omip-runtime` | Simulation environment snapshots |
| `omip-mqtt-data` | Mosquitto persistence |
| `omip-mqtt-logs` | Mosquitto logs |

List volumes:

```powershell
docker volume ls --filter name=omip
```

## Complete reset

This action permanently deletes all Docker-managed OMIP data:

```powershell
.\scripts\docker-reset.cmd
```

The script requires the exact confirmation phrase `DELETE OMIP DATA`.

## Local-network access

The default `.env.example` binds HTTP and MQTT to `127.0.0.1`, so they are only
available on the local machine.

For a trusted LAN, set:

```dotenv
OMIP_BIND_ADDRESS=0.0.0.0
```

Then configure the host firewall. Do not expose this Foundation deployment
directly to the public Internet.

## Security boundary

The bundled Mosquitto configuration allows anonymous clients to support a
zero-configuration local demo. Before remote deployment, add:

- MQTT usernames and passwords;
- topic ACLs;
- MQTT TLS;
- HTTPS/WSS termination;
- API authentication;
- restricted CORS;
- secret management.

## Database scope

This deployment intentionally retains SQLite because OMIP v0.5.3 currently
uses a SQLite repository implementation. PostgreSQL requires an application
repository and migration change and is planned as a separate deployment phase.
