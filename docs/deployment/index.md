# Deployment

OMIP deployment is being developed in stages.

## Current stages

1. Local Python development
2. Local Docker Compose
3. Linux LAN server
4. Secure remote deployment
5. Cloud reference architecture

## Deployment requirements

Public or shared deployment must address:

- persistent storage;
- backup and recovery;
- HTTPS and WSS;
- authenticated MQTT over TLS;
- MQTT topic ACLs;
- secret management;
- restricted CORS;
- health checks and restart policies.

The next Foundation task is a reproducible local Docker Compose deployment.
