# OMIP Quick Start Guide

Version: v1.0

Estimated setup time: **~5 minutes**

## Prerequisites

- Git
- Docker Desktop
- Python 3.12+

Verify:

```bash
git --version
docker --version
docker compose version
python --version
```

## Clone

```bash
git clone https://github.com/omip-project/omip.git
cd omip
```

## Configure

Windows:

```powershell
copy .env.example .env
```

If port 8000 is unavailable:

```text
OMIP_HTTP_PORT=18080
```

## Start

```bash
docker compose up -d --build
```

Verify:

```bash
docker compose ps
```

## Dashboard

- http://localhost:18080
- http://localhost:18080/docs

## Demo

```bash
docker compose --profile demo up
```

## Verify

- MQTT = ON
- Vehicle = ONLINE
- Mission = RUNNING
- Heartbeat updating
- Telemetry updating

## Stop

```bash
docker compose down
```

See also:

- INSTALL.md
- TROUBLESHOOTING.md
- FAQ.md
