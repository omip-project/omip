# Architecture

OMIP provides a vehicle-independent mission data and operational layer.

```text
Vehicles and simulators
        │
        ├── HTTP
        └── MQTT
             │
             ▼
      Acquisition layer
             │
     ┌───────┴────────┐
     ▼                ▼
Raw message store   Normalisation
                         │
                         ▼
                 Unified telemetry
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Mission data   Environment     Integrity and
      and replay     context         safety analytics
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                  Dashboard and API
                         │
                         ▼
               Export, datasets, research
```

## Design principles

- Preserve raw data.
- Provide versioned normalised contracts.
- Keep mission configuration reproducible.
- Separate stable platform capabilities from experimental research.
- Support type-specific behaviour through vehicle profiles.
- Treat observability and integrity as first-class concerns.
