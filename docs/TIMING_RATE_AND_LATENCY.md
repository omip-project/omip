# OMIP v0.4.1 Timing, Rate and Latency Guide

## Quick demonstration

Run the backend, then use one of these scenarios:

```powershell
.\scripts\run_simulator.cmd --vehicle-id OMIP-SIM-002 --scenario .\scenarios\low_sampling_rate.json --duration 24
.\scripts\run_simulator.cmd --vehicle-id OMIP-SIM-003 --scenario .\scenarios\high_latency.json --duration 20
.\scripts\run_simulator.cmd --vehicle-id OMIP-SIM-004 --scenario .\scenarios\timestamp_faults.json --duration 24
.\scripts\run_simulator.cmd --vehicle-id OMIP-SIM-005 --scenario .\scenarios\combined_timing_faults.json --duration 30
```

Select the completed Mission in the Operations Console to view the Sensor Integrity Metrics table.

## Fault fields supported by the simulator

```json
{
  "faults": {
    "sensor_rate_multipliers": {"GNSS": 0.25},
    "timing_fault_sensor_types": ["GNSS"],
    "delay_every_n_messages": 8,
    "delay_ms": 2500,
    "timestamp_regression_every_n_messages": 30,
    "timestamp_regression_ms": 3000,
    "future_timestamp_every_n_messages": 45,
    "future_timestamp_ms": 12000
  }
}
```

`delay_ms` changes the device timestamp rather than sleeping the simulator thread. This makes the intended communication-latency condition reproducible without blocking the other sensor streams.

## Interpreting metrics

`actual_rate_hz` is calculated from server receipt times. It therefore measures the rate observed by OMIP, not only the producer's configured loop frequency.

Latency percentiles are calculated across stored message latency values for the selected Sensor and optional Mission.

A healthy metric summary does not delete old Integrity Events. It means no currently active Alert remains for that condition.
