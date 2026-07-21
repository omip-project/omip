# OMIP v0.4.2 MQTT Setup

## Start Mosquitto

With Docker Desktop:

```powershell
.\scripts\run_mqtt_broker.cmd
```

or:

```powershell
docker compose up -d mosquitto
```

Verify:

```powershell
Test-NetConnection 127.0.0.1 -Port 1883
```

## Enable from the browser

1. Open `http://127.0.0.1:8000`.
2. In the MQTT card, select **Configure**.
3. Set host to `127.0.0.1` and port to `1883`.
4. Select **Save and enable**.

The MQTT state should move from `WAIT` to `ON` after the broker connection completes.

Use **Disable** to stop the OMIP MQTT bridge. HTTP ingestion remains active.

## API control

Enable:

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri http://127.0.0.1:8000/api/v1/acquisition/mqtt `
  -ContentType application/json `
  -Body '{"enabled":true,"host":"127.0.0.1","port":1883}'
```

Disable:

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri http://127.0.0.1:8000/api/v1/acquisition/mqtt `
  -ContentType application/json `
  -Body '{"enabled":false}'
```

Status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/acquisition/status
```

## Automatic startup

```powershell
$env:OMIP_MQTT_ENABLED="true"
$env:OMIP_MQTT_HOST="127.0.0.1"
$env:OMIP_MQTT_PORT="1883"
.\scripts\run_backend.cmd
```

The browser switch is runtime-only and does not rewrite environment variables.
