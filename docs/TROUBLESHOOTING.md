# Troubleshooting

## Port 8000 unavailable

Set:

```text
OMIP_HTTP_PORT=18080
```

## PowerShell execution policy

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Docker not running

Start Docker Desktop.

## MQTT WAIT

Ensure latest MQTT compatibility patch is applied and backend connects successfully.

## Demo vehicle missing

Run:

```bash
docker compose --profile demo up
```
