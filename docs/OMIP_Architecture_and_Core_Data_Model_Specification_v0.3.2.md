# OMIP Architecture and Core Data Model Specification v0.3.2

## 1. Release purpose

OMIP v0.3.2 is a corrective release for the v0.3 acquisition architecture. It addresses two operational issues found during multi-vehicle use:

1. fleet-summary cards were incorrectly affected by the selected-vehicle filter;
2. MQTT could only be enabled through startup environment variables.

No breaking change is introduced to TelemetryFrame, RawSensorMessage or VehicleHeartbeat data contracts. The current wire schema remains v0.3.1-compatible.

## 2. Dashboard state model

The browser maintains two distinct concepts:

- **fleet state**: all vehicles, all sensors and global counts;
- **view filter**: the vehicle or Mission selected for detailed panels.

Global summary metrics must be derived from the complete API result:

```text
vehicle_count       = count(all registered vehicles)
active_vehicle_count= count(ONLINE vehicles with an active Mission)
sensor_count        = count(all registered sensors)
online_sensor_count = count(ONLINE sensors)
raw_message_count   = sum(raw-message count for all vehicles)
```

Changing `selectedVehicle` must not change these values.

## 3. Vehicle selection behavior

Incoming telemetry is not an operator selection event. Therefore, a WebSocket message must not modify `selectedVehicle`.

When no vehicle is selected:

- the selector remains on `All vehicles`;
- Fleet Registry shows the complete registry;
- Sensor Registry shows all sensors;
- the trajectory panel may draw one trajectory per vehicle;
- raw-message view shows recent messages from the fleet.

When a vehicle is explicitly selected:

- Sensor Registry, raw messages and live trajectory are filtered;
- fleet summary cards and Fleet Registry remain global;
- the selected row is highlighted.

## 4. Runtime MQTT architecture

```text
Dashboard
   │ PUT /api/v1/acquisition/mqtt
   ▼
FastAPI control endpoint
   ▼
MqttRuntimeManager
   ├── enable/reconfigure
   ├── disable
   └── status
          │
          ▼
      MqttBridge
          │
          ▼
External MQTT broker
```

`MqttRuntimeManager` owns exactly one bridge instance and serializes state changes with an asynchronous lock.

### 4.1 Enable request

```json
{
  "enabled": true,
  "host": "127.0.0.1",
  "port": 1883,
  "raw_topic": "omip/+/sensors/+",
  "telemetry_topic": "omip/+/telemetry",
  "heartbeat_topic": "omip/+/heartbeat"
}
```

Only `enabled` is mandatory. Omitted connection values retain the current runtime configuration.

### 4.2 Disable request

```json
{
  "enabled": false
}
```

Disabling MQTT stops the Paho network loop and disconnects the bridge. HTTP ingestion remains available.

### 4.3 Runtime status

```json
{
  "enabled": true,
  "started": true,
  "connected": true,
  "host": "127.0.0.1",
  "port": 1883,
  "raw_topic": "omip/+/sensors/+",
  "telemetry_topic": "omip/+/telemetry",
  "heartbeat_topic": "omip/+/heartbeat",
  "last_error": null,
  "last_changed_at_utc": "2026-07-18T08:00:00+00:00"
}
```

## 5. MQTT state presentation

```text
OFF    enabled=false
WAIT   enabled=true, connected=false, no immediate error
ON     enabled=true, connected=true
ERROR  enabled=true, last_error is present
```

The MQTT switch controls only the OMIP consumer. Broker lifecycle is outside the HTTP service boundary.

## 6. Safety and deployment notes

The runtime-control endpoint is intended for local development and trusted operational networks. v0.3.2 does not yet provide authentication or role-based access control. Public deployment must place the API behind an authenticated gateway before exposing MQTT configuration.

Runtime settings are in-memory and revert to environment-variable defaults after backend restart.

## 7. Compatibility

The following interfaces remain compatible:

- v0.2 Telemetry ingestion;
- v0.3 and v0.3.1 raw sensor messages;
- v0.3.1 heartbeat messages;
- Mission, Vehicle, Sensor and Event APIs;
- HTTP and MQTT topic structures;
- CSV and JSONL exports.

## 8. Acceptance criteria

A release is accepted when:

1. registering two vehicles results in `Vehicles = 2` regardless of selected vehicle;
2. selecting a vehicle does not alter global summary cards;
3. fleet view remains selected while messages arrive;
4. multiple live trajectories can be displayed in fleet view;
5. MQTT can be enabled and disabled through the dashboard;
6. host and port can be changed without backend restart;
7. disabling MQTT leaves HTTP ingestion operational;
8. automated tests pass.
