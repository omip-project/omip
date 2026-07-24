from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .repositories import VehicleProfileRepository
from .schemas import (IntegrityFinding, MissionCreate, MissionEventCreate,
                      MissionEventUpdate, MissionStatus, RawSensorMessage,
                      SensorCreate, SensorUpdate, SimulationRunCreate,
                      TelemetryFrame, TransportType, VehicleCreate,
                      VehicleHeartbeat, VehicleProfileCreate,
                      VehicleProfileUpdate, VehicleUpdate)


class OmipRepository:
    """SQLite persistence for the OMIP v0.5.2 acquisition, integrity and operational monitoring platform."""

    def __init__(
        self,
        database_path: Path,
        online_threshold_s: float = 5.0,
        degraded_threshold_s: float = 15.0,
    ) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._online_threshold_s = online_threshold_s
        self._degraded_threshold_s = degraded_threshold_s
        self._initialise()
        self._vehicle_profiles = VehicleProfileRepository(
            connect=self._connect,
            lock=self._lock,
            utc_now=self._utc_now,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id TEXT PRIMARY KEY,
                    vehicle_name TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT
                );

                CREATE TABLE IF NOT EXISTS vehicle_parameter_definitions (
                    vehicle_type TEXT NOT NULL,
                    parameter_path TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (vehicle_type, parameter_path)
                );

                CREATE TABLE IF NOT EXISTS vehicle_profiles (
                    profile_id TEXT PRIMARY KEY,
                    profile_name TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    capabilities_json TEXT NOT NULL DEFAULT '{}',
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sensors (
                    sensor_id TEXT PRIMARY KEY,
                    vehicle_id TEXT NOT NULL,
                    sensor_name TEXT NOT NULL,
                    sensor_type TEXT NOT NULL,
                    manufacturer TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    unit TEXT NOT NULL DEFAULT '',
                    sampling_rate_hz REAL,
                    coordinate_frame TEXT NOT NULL DEFAULT 'LOCAL_ENU',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT,
                    last_transport TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    invalid_message_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                );

                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    vehicle_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    scenario_name TEXT,
                    status TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    started_at_utc TEXT,
                    ended_at_utc TEXT
                );

                CREATE TABLE IF NOT EXISTS simulation_runs (
                    run_id TEXT PRIMARY KEY,
                    vehicle_id TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    vehicle_profile_id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_s REAL NOT NULL,
                    transport TEXT NOT NULL,
                    random_seed INTEGER NOT NULL,
                    parameter_overrides_json TEXT NOT NULL DEFAULT '{}',
                    effective_parameters_json TEXT NOT NULL DEFAULT '{}',
                    command_json TEXT NOT NULL DEFAULT '[]',
                    process_id INTEGER,
                    exit_code INTEGER,
                    error_message TEXT,
                    log_path TEXT,
                    stop_reason TEXT,
                    created_at_utc TEXT NOT NULL,
                    started_at_utc TEXT,
                    ended_at_utc TEXT,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY (vehicle_profile_id) REFERENCES vehicle_profiles(profile_id)
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_runs_created
                    ON simulation_runs(created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_simulation_runs_vehicle
                    ON simulation_runs(vehicle_id, created_at_utc DESC);

                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    vehicle_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    x_m REAL NOT NULL,
                    y_m REAL NOT NULL,
                    z_m REAL NOT NULL,
                    speed_mps REAL NOT NULL,
                    battery_percent REAL NOT NULL,
                    operating_mode TEXT NOT NULL,
                    valid INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    coordinate_frame TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                );

                CREATE TABLE IF NOT EXISTS raw_sensor_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    vehicle_id TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    message_type TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    topic TEXT,
                    valid INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                );

                CREATE TABLE IF NOT EXISTS vehicle_heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    vehicle_id TEXT NOT NULL,
                    mission_id TEXT,
                    timestamp_utc TEXT NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    state TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                );

                CREATE TABLE IF NOT EXISTS mission_events (
                    event_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    start_timestamp_utc TEXT NOT NULL,
                    end_timestamp_utc TEXT,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id),
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
                );

                CREATE TABLE IF NOT EXISTS integrity_events (
                    integrity_event_id TEXT PRIMARY KEY,
                    dedup_key TEXT NOT NULL UNIQUE,
                    stream_kind TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    sensor_id TEXT,
                    mission_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    detected_at_utc TEXT NOT NULL,
                    description TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    active_key TEXT,
                    integrity_event_id TEXT,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    sensor_id TEXT,
                    mission_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    first_detected_at_utc TEXT NOT NULL,
                    last_detected_at_utc TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    acknowledged_at_utc TEXT,
                    acknowledged_by TEXT,
                    resolved_at_utc TEXT,
                    resolved_by TEXT,
                    resolution_source TEXT,
                    resolution_reason TEXT,
                    operator_note TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (integrity_event_id) REFERENCES integrity_events(integrity_event_id),
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                );

                CREATE TABLE IF NOT EXISTS application_logs (
                    log_id TEXT PRIMARY KEY,
                    timestamp_utc TEXT NOT NULL,
                    level TEXT NOT NULL,
                    component TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    vehicle_id TEXT,
                    sensor_id TEXT,
                    mission_id TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS system_metric_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    timestamp_utc TEXT NOT NULL,
                    overall_status TEXT NOT NULL,
                    uptime_seconds REAL NOT NULL,
                    raw_rate_per_second REAL NOT NULL DEFAULT 0.0,
                    telemetry_rate_per_second REAL NOT NULL DEFAULT 0.0,
                    http_rate_per_second REAL NOT NULL DEFAULT 0.0,
                    mqtt_rate_per_second REAL NOT NULL DEFAULT 0.0,
                    database_write_latency_ms REAL,
                    database_query_latency_ms REAL,
                    websocket_clients INTEGER NOT NULL DEFAULT 0,
                    memory_usage_mb REAL,
                    cpu_percent REAL,
                    open_alerts INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS platform_alerts (
                    alert_id TEXT PRIMARY KEY,
                    active_key TEXT UNIQUE,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    component TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    first_detected_at_utc TEXT NOT NULL,
                    last_detected_at_utc TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    resolved_at_utc TEXT,
                    resolved_by TEXT,
                    resolution_source TEXT,
                    resolution_reason TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_time
                    ON telemetry(vehicle_id, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_mission_time
                    ON telemetry(mission_id, timestamp_utc ASC, id ASC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_mission_sequence
                    ON telemetry(mission_id, sequence_no ASC);
                CREATE INDEX IF NOT EXISTS idx_raw_vehicle_time
                    ON raw_sensor_messages(vehicle_id, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_raw_sensor_time
                    ON raw_sensor_messages(sensor_id, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_raw_mission_time
                    ON raw_sensor_messages(mission_id, timestamp_utc ASC, id ASC);
                CREATE INDEX IF NOT EXISTS idx_events_mission_time
                    ON mission_events(mission_id, start_timestamp_utc ASC);
                CREATE INDEX IF NOT EXISTS idx_heartbeats_vehicle_received
                    ON vehicle_heartbeats(vehicle_id, received_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_heartbeats_mission_received
                    ON vehicle_heartbeats(mission_id, received_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_missions_vehicle_created
                    ON missions(vehicle_id, created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_sensors_vehicle
                    ON sensors(vehicle_id, sensor_id);
                CREATE INDEX IF NOT EXISTS idx_integrity_mission_time
                    ON integrity_events(mission_id, detected_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_integrity_sensor_time
                    ON integrity_events(sensor_id, detected_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_integrity_type_time
                    ON integrity_events(check_type, detected_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_status_time
                    ON alerts(status, last_detected_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_mission_time
                    ON alerts(mission_id, last_detected_at_utc DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_active_key
                    ON alerts(active_key) WHERE active_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_application_logs_time
                    ON application_logs(timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_application_logs_level_component
                    ON application_logs(level, component, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_system_snapshots_time
                    ON system_metric_snapshots(timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_platform_alerts_status_time
                    ON platform_alerts(status, last_detected_at_utc DESC);
                """)

            # Preserve compatibility when a v0.2 database is copied into v0.3.
            telemetry_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(telemetry)").fetchall()
            }
            migrations = {
                "latency_ms": "REAL NOT NULL DEFAULT 0.0",
                "valid": "INTEGER NOT NULL DEFAULT 1",
                "confidence": "REAL NOT NULL DEFAULT 1.0",
                "source": "TEXT NOT NULL DEFAULT 'legacy-v0.1'",
                "coordinate_frame": "TEXT NOT NULL DEFAULT 'LOCAL_ENU'",
            }
            for name, definition in migrations.items():
                if name not in telemetry_columns:
                    connection.execute(
                        f"ALTER TABLE telemetry ADD COLUMN {name} {definition}"
                    )

            vehicle_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(vehicles)").fetchall()
            }
            vehicle_migrations = {
                "vehicle_profile_id": "TEXT",
                "capabilities_json": "TEXT NOT NULL DEFAULT '{}'",
                "parameters_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for name, definition in vehicle_migrations.items():
                if name not in vehicle_columns:
                    connection.execute(
                        f"ALTER TABLE vehicles ADD COLUMN {name} {definition}"
                    )

            alert_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(alerts)").fetchall()
            }
            alert_migrations = {
                "resolution_source": "TEXT",
                "resolution_reason": "TEXT",
            }
            for name, definition in alert_migrations.items():
                if name not in alert_columns:
                    connection.execute(
                        f"ALTER TABLE alerts ADD COLUMN {name} {definition}"
                    )

            platform_alert_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(platform_alerts)"
                ).fetchall()
            }
            platform_alert_migrations = {
                "acknowledged_at_utc": "TEXT",
                "acknowledged_by": "TEXT",
                "operator_note": "TEXT NOT NULL DEFAULT ''",
            }
            for name, definition in platform_alert_migrations.items():
                if name not in platform_alert_columns:
                    connection.execute(
                        f"ALTER TABLE platform_alerts ADD COLUMN {name} {definition}"
                    )

            now = self._utc_now().isoformat()
            legacy_vehicles = connection.execute("""
                SELECT vehicle_id FROM missions
                UNION
                SELECT vehicle_id FROM telemetry
                """).fetchall()
            for row in legacy_vehicles:
                vehicle_id = str(row["vehicle_id"])
                connection.execute(
                    """
                    INSERT OR IGNORE INTO vehicles (
                        vehicle_id, vehicle_name, vehicle_type, description,
                        created_at_utc, updated_at_utc
                    ) VALUES (?, ?, 'SIMULATED', ?, ?, ?)
                    """,
                    (
                        vehicle_id,
                        vehicle_id,
                        "Automatically registered while migrating an earlier OMIP database.",
                        now,
                        now,
                    ),
                )

            legacy_missions = connection.execute("""
                SELECT mission_id, vehicle_id, MIN(timestamp_utc) AS first_time,
                       MAX(timestamp_utc) AS last_time
                FROM telemetry
                GROUP BY mission_id, vehicle_id
                """).fetchall()
            for row in legacy_missions:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO missions (
                        mission_id, vehicle_id, name, scenario_name, status,
                        description, metadata_json, created_at_utc,
                        started_at_utc, ended_at_utc
                    ) VALUES (?, ?, ?, NULL, 'COMPLETED', ?, '{}', ?, ?, ?)
                    """,
                    (
                        row["mission_id"],
                        row["vehicle_id"],
                        f"Imported mission {row['mission_id']}",
                        "Automatically imported from an earlier OMIP telemetry database.",
                        row["first_time"],
                        row["first_time"],
                        row["last_time"],
                    ),
                )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _generated_id(prefix: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{prefix}-{stamp}-{uuid4().hex[:6].upper()}"

    @staticmethod
    def _load_json(value: str | None) -> dict[str, Any]:
        try:
            return json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}

    def _age_seconds(self, timestamp: str | None) -> float | None:
        if not timestamp:
            return None
        try:
            seen = datetime.fromisoformat(timestamp)
            if seen.tzinfo is None or seen.utcoffset() is None:
                seen = seen.replace(tzinfo=timezone.utc)
            return max(
                0.0, (self._utc_now() - seen.astimezone(timezone.utc)).total_seconds()
            )
        except ValueError:
            return None

    def _connection_status(
        self, last_seen: str | None, enabled: bool
    ) -> tuple[str, float | None]:
        if not enabled:
            return "DISABLED", None
        age_s = self._age_seconds(last_seen)
        if age_s is None:
            return "UNKNOWN", None
        if age_s <= self._online_threshold_s:
            return "ONLINE", age_s
        if age_s <= self._degraded_threshold_s:
            return "DEGRADED", age_s
        return "OFFLINE", age_s

    @staticmethod
    def _latest_timestamp(*values: str | None) -> str | None:
        parsed: list[tuple[datetime, str]] = []
        for value in values:
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None or dt.utcoffset() is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed.append((dt.astimezone(timezone.utc), value))
            except ValueError:
                continue
        return max(parsed, key=lambda item: item[0])[1] if parsed else None

    def _decode_vehicle(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["enabled"] = bool(record["enabled"])
        record["metadata"] = self._load_json(record.pop("metadata_json", "{}"))
        record["capabilities"] = self._load_json(record.pop("capabilities_json", "{}"))
        record["parameters"] = self._load_json(record.pop("parameters_json", "{}"))
        activity_at = self._latest_timestamp(
            record.get("last_seen_at_utc"), record.get("last_heartbeat_received_at_utc")
        )
        record["last_activity_at_utc"] = activity_at
        active_mission_id = record.get("active_mission_id")
        latest_mission_status = record.get("latest_mission_status")
        if not record["enabled"]:
            status, age_s, reason = "DISABLED", None, "Vehicle is disabled"
        elif active_mission_id:
            status, age_s = self._connection_status(activity_at, True)
            if status == "ONLINE":
                reason = "Running mission and recent heartbeat or telemetry"
            elif status == "DEGRADED":
                reason = "Running mission but activity is delayed"
            elif status == "OFFLINE":
                reason = "Running mission with no recent heartbeat or telemetry"
            else:
                reason = "Running mission has not produced activity yet"
        elif latest_mission_status or activity_at:
            status, age_s, reason = (
                "INACTIVE",
                self._age_seconds(activity_at),
                "No mission is currently running",
            )
        else:
            status, age_s, reason = (
                "UNKNOWN",
                None,
                "No mission or vehicle activity has been recorded",
            )
        record["connection_status"] = status
        record["connection_status_reason"] = reason
        record["activity_age_s"] = round(age_s, 3) if age_s is not None else None
        return record

    def _decode_sensor(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["enabled"] = bool(record["enabled"])
        record["metadata"] = self._load_json(record.pop("metadata_json", "{}"))
        if not record["enabled"]:
            status, age_s, reason = "DISABLED", None, "Sensor is disabled"
        elif not record.get("active_mission_id"):
            if record.get("latest_mission_status") or record.get("last_seen_at_utc"):
                status, age_s, reason = (
                    "INACTIVE",
                    self._age_seconds(record.get("last_seen_at_utc")),
                    "No mission is currently running",
                )
            else:
                status, age_s, reason = "UNKNOWN", None, "Sensor has not produced data"
        else:
            status, age_s = self._connection_status(
                record.get("last_seen_at_utc"), True
            )
            reasons = {
                "ONLINE": "Sensor data is arriving normally",
                "DEGRADED": "Sensor data is arriving late",
                "OFFLINE": "Running mission but sensor data has stopped",
                "UNKNOWN": "Running mission but sensor has not produced data",
            }
            reason = reasons.get(status, status)
        record["connection_status"] = status
        record["connection_status_reason"] = reason
        record["activity_age_s"] = round(age_s, 3) if age_s is not None else None
        return record

    @staticmethod
    def _decode_mission(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    @staticmethod
    def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    @staticmethod
    def _decode_integrity_event(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["details"] = json.loads(record.pop("details_json") or "{}")
        return record

    @staticmethod
    def _decode_alert(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    @staticmethod
    def _decode_vehicle_profile(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["capabilities"] = json.loads(record.pop("capabilities_json") or "{}")
        record["parameters"] = json.loads(record.pop("parameters_json") or "{}")
        record["enabled"] = bool(record["enabled"])
        record["built_in"] = bool(record["built_in"])
        return record

    @staticmethod
    def _decode_simulation_run(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["parameter_overrides"] = json.loads(
            record.pop("parameter_overrides_json") or "{}"
        )
        record["effective_parameters"] = json.loads(
            record.pop("effective_parameters_json") or "{}"
        )
        record["command"] = json.loads(record.pop("command_json") or "[]")
        return record

    # ------------------------------------------------------------------
    # Vehicle profiles and parameter definitions
    # ------------------------------------------------------------------
    def seed_vehicle_parameter_definitions(
        self, definitions: dict[str, dict[str, dict[str, Any]]]
    ) -> None:
        self._vehicle_profiles.seed_vehicle_parameter_definitions(definitions)

    def list_vehicle_parameter_definitions(
        self, vehicle_type: str | None = None
    ) -> list[dict[str, Any]]:
        return self._vehicle_profiles.list_vehicle_parameter_definitions(vehicle_type)

    def upsert_vehicle_profile(
        self, request: VehicleProfileCreate, *, built_in: bool = False
    ) -> dict[str, Any]:
        return self._vehicle_profiles.upsert_vehicle_profile(
            request, built_in=built_in
        )

    def get_vehicle_profile(self, profile_id: str) -> dict[str, Any] | None:
        return self._vehicle_profiles.get_vehicle_profile(profile_id)

    def list_vehicle_profiles(
        self, vehicle_type: str | None = None, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        return self._vehicle_profiles.list_vehicle_profiles(
            vehicle_type=vehicle_type, enabled_only=enabled_only
        )

    def update_vehicle_profile(
        self, profile_id: str, request: VehicleProfileUpdate
    ) -> dict[str, Any] | None:
        return self._vehicle_profiles.update_vehicle_profile(profile_id, request)

    def delete_vehicle_profile(self, profile_id: str) -> bool:
        return self._vehicle_profiles.delete_vehicle_profile(profile_id)

    # ------------------------------------------------------------------
    # Simulation runs
    # ------------------------------------------------------------------
    def create_simulation_run_record(
        self,
        run_id: str,
        request: SimulationRunCreate,
        mission_id: str,
        effective_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO simulation_runs (run_id, vehicle_id, vehicle_type, vehicle_profile_id, scenario_id, mission_id,
                    status, duration_s, transport, random_seed, parameter_overrides_json, effective_parameters_json,
                    created_at_utc, updated_at_utc) VALUES (?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    request.vehicle_id,
                    request.vehicle_type,
                    request.vehicle_profile_id,
                    request.scenario_id,
                    mission_id,
                    request.duration_s,
                    request.transport,
                    request.random_seed,
                    json.dumps(request.parameter_overrides, separators=(",", ":")),
                    json.dumps(effective_parameters, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        record = self.get_simulation_run(run_id)
        if record is None:
            raise RuntimeError("Simulation run was not created")
        return record

    def update_simulation_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        command: list[str] | None = None,
        process_id: int | None = None,
        exit_code: int | None = None,
        error_message: str | None = None,
        log_path: str | None = None,
        stop_reason: str | None = None,
        mark_started: bool = False,
        mark_ended: bool = False,
    ) -> dict[str, Any] | None:
        assignments: list[str] = ["updated_at_utc = ?"]
        params: list[Any] = [self._utc_now().isoformat()]
        for column, value in (
            ("status", status),
            ("process_id", process_id),
            ("exit_code", exit_code),
            ("error_message", error_message),
            ("log_path", log_path),
            ("stop_reason", stop_reason),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                params.append(value)
        if command is not None:
            assignments.append("command_json = ?")
            params.append(json.dumps(command))
        if mark_started:
            assignments.append("started_at_utc = COALESCE(started_at_utc, ?)")
            params.append(self._utc_now().isoformat())
        if mark_ended:
            assignments.append("ended_at_utc = COALESCE(ended_at_utc, ?)")
            params.append(self._utc_now().isoformat())
        params.append(run_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE simulation_runs SET {', '.join(assignments)} WHERE run_id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_simulation_run(run_id)

    def get_simulation_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM simulation_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._decode_simulation_run(row) if row else None

    def list_simulation_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM simulation_runs ORDER BY created_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode_simulation_run(row) for row in rows]

    # ------------------------------------------------------------------
    # Vehicle registry
    # ------------------------------------------------------------------
    def create_vehicle(self, request: VehicleCreate) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicles (
                    vehicle_id, vehicle_name, vehicle_type, manufacturer, model,
                    description, enabled, vehicle_profile_id, capabilities_json, parameters_json,
                    metadata_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.vehicle_id,
                    request.vehicle_name,
                    request.vehicle_type,
                    request.manufacturer,
                    request.model,
                    request.description,
                    1 if request.enabled else 0,
                    request.vehicle_profile_id,
                    json.dumps(request.capabilities, separators=(",", ":")),
                    json.dumps(request.parameters, separators=(",", ":")),
                    json.dumps(request.metadata, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        vehicle = self.get_vehicle(request.vehicle_id)
        if vehicle is None:
            raise RuntimeError("Vehicle was not created")
        return vehicle

    def ensure_vehicle(self, vehicle_id: str) -> None:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO vehicles (
                    vehicle_id, vehicle_name, vehicle_type, description,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, 'SIMULATED', ?, ?, ?)
                """,
                (
                    vehicle_id,
                    vehicle_id,
                    "Automatically registered by the acquisition layer.",
                    now,
                    now,
                ),
            )

    def get_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT v.*,
                    (SELECT COUNT(*) FROM sensors s WHERE s.vehicle_id = v.vehicle_id) AS sensor_count,
                    (SELECT COUNT(*) FROM missions m WHERE m.vehicle_id = v.vehicle_id) AS mission_count,
                    (SELECT COUNT(*) FROM telemetry t WHERE t.vehicle_id = v.vehicle_id) AS telemetry_count,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.vehicle_id = v.vehicle_id) AS raw_message_count,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = v.vehicle_id AND m.status = 'RUNNING' ORDER BY m.started_at_utc DESC LIMIT 1) AS active_mission_id,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = v.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_id,
                    (SELECT m.status FROM missions m WHERE m.vehicle_id = v.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_status,
                    (SELECT h.received_at_utc FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_received_at_utc,
                    (SELECT h.timestamp_utc FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_timestamp_utc,
                    (SELECT h.state FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_state,
                    (SELECT h.transport FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_transport,
                    (SELECT COUNT(*) FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id) AS heartbeat_count
                FROM vehicles v WHERE v.vehicle_id = ?
                """,
                (vehicle_id,),
            ).fetchone()
        return self._decode_vehicle(row) if row else None

    def list_vehicles(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT v.*,
                    (SELECT COUNT(*) FROM sensors s WHERE s.vehicle_id = v.vehicle_id) AS sensor_count,
                    (SELECT COUNT(*) FROM missions m WHERE m.vehicle_id = v.vehicle_id) AS mission_count,
                    (SELECT COUNT(*) FROM telemetry t WHERE t.vehicle_id = v.vehicle_id) AS telemetry_count,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.vehicle_id = v.vehicle_id) AS raw_message_count,
                    (SELECT MAX(t.timestamp_utc) FROM telemetry t WHERE t.vehicle_id = v.vehicle_id) AS latest_timestamp_utc,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = v.vehicle_id AND m.status = 'RUNNING' ORDER BY m.started_at_utc DESC LIMIT 1) AS active_mission_id,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = v.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_id,
                    (SELECT m.status FROM missions m WHERE m.vehicle_id = v.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_status,
                    (SELECT h.received_at_utc FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_received_at_utc,
                    (SELECT h.timestamp_utc FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_timestamp_utc,
                    (SELECT h.state FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_state,
                    (SELECT h.transport FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id ORDER BY h.received_at_utc DESC, h.id DESC LIMIT 1) AS last_heartbeat_transport,
                    (SELECT COUNT(*) FROM vehicle_heartbeats h WHERE h.vehicle_id = v.vehicle_id) AS heartbeat_count
                FROM vehicles v
                ORDER BY v.vehicle_id
                """).fetchall()
        return [self._decode_vehicle(row) for row in rows]

    def update_vehicle(
        self, vehicle_id: str, request: VehicleUpdate
    ) -> dict[str, Any] | None:
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return self.get_vehicle(vehicle_id)
        mapping = {
            "vehicle_name": "vehicle_name",
            "vehicle_type": "vehicle_type",
            "manufacturer": "manufacturer",
            "model": "model",
            "description": "description",
            "enabled": "enabled",
            "vehicle_profile_id": "vehicle_profile_id",
            "capabilities": "capabilities_json",
            "parameters": "parameters_json",
            "metadata": "metadata_json",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{mapping[key]} = ?")
            if key == "enabled":
                value = 1 if value else 0
            elif key in {"metadata", "capabilities", "parameters"}:
                value = json.dumps(value, separators=(",", ":"))
            params.append(value)
        assignments.append("updated_at_utc = ?")
        params.append(self._utc_now().isoformat())
        params.append(vehicle_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE vehicles SET {', '.join(assignments)} WHERE vehicle_id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_vehicle(vehicle_id)

    def delete_vehicle(self, vehicle_id: str) -> bool:
        with self._lock, self._connect() as connection:
            dependent = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM sensors WHERE vehicle_id = ?) +
                    (SELECT COUNT(*) FROM missions WHERE vehicle_id = ?) +
                    (SELECT COUNT(*) FROM telemetry WHERE vehicle_id = ?) +
                    (SELECT COUNT(*) FROM raw_sensor_messages WHERE vehicle_id = ?) +
                    (SELECT COUNT(*) FROM vehicle_heartbeats WHERE vehicle_id = ?) AS total
                """,
                (vehicle_id, vehicle_id, vehicle_id, vehicle_id, vehicle_id),
            ).fetchone()
            if dependent and int(dependent["total"]) > 0:
                raise ValueError(
                    "Vehicle has dependent sensors, missions or data; disable it instead"
                )
            cursor = connection.execute(
                "DELETE FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Sensor registry
    # ------------------------------------------------------------------
    def create_sensor(self, vehicle_id: str, request: SensorCreate) -> dict[str, Any]:
        self.ensure_vehicle(vehicle_id)
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sensors (
                    sensor_id, vehicle_id, sensor_name, sensor_type, manufacturer,
                    model, unit, sampling_rate_hz, coordinate_frame, enabled,
                    metadata_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.sensor_id,
                    vehicle_id,
                    request.sensor_name,
                    request.sensor_type,
                    request.manufacturer,
                    request.model,
                    request.unit,
                    request.sampling_rate_hz,
                    request.coordinate_frame,
                    1 if request.enabled else 0,
                    json.dumps(request.metadata, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        sensor = self.get_sensor(request.sensor_id)
        if sensor is None:
            raise RuntimeError("Sensor was not created")
        return sensor

    def ensure_sensor(self, message: RawSensorMessage) -> None:
        self.ensure_vehicle(message.vehicle_id)
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sensors (
                    sensor_id, vehicle_id, sensor_name, sensor_type,
                    coordinate_frame, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, 'LOCAL_ENU', ?, ?)
                """,
                (
                    message.sensor_id,
                    message.vehicle_id,
                    message.sensor_id,
                    message.message_type,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT vehicle_id FROM sensors WHERE sensor_id = ?",
                (message.sensor_id,),
            ).fetchone()
            if row and row["vehicle_id"] != message.vehicle_id:
                raise ValueError(
                    f"Sensor {message.sensor_id} is registered to vehicle {row['vehicle_id']}"
                )

    def get_sensor(self, sensor_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.sensor_id = s.sensor_id) AS stored_message_count,
                    (SELECT MAX(r.timestamp_utc) FROM raw_sensor_messages r WHERE r.sensor_id = s.sensor_id) AS latest_timestamp_utc,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = s.vehicle_id AND m.status = 'RUNNING' ORDER BY m.started_at_utc DESC LIMIT 1) AS active_mission_id,
                    (SELECT m.status FROM missions m WHERE m.vehicle_id = s.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_status
                FROM sensors s WHERE s.sensor_id = ?
                """,
                (sensor_id,),
            ).fetchone()
        return self._decode_sensor(row) if row else None

    def list_sensors(self, vehicle_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE s.vehicle_id = ?" if vehicle_id else ""
        params: tuple[Any, ...] = (vehicle_id,) if vehicle_id else ()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.*,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.sensor_id = s.sensor_id) AS stored_message_count,
                    (SELECT MAX(r.timestamp_utc) FROM raw_sensor_messages r WHERE r.sensor_id = s.sensor_id) AS latest_timestamp_utc,
                    (SELECT m.mission_id FROM missions m WHERE m.vehicle_id = s.vehicle_id AND m.status = 'RUNNING' ORDER BY m.started_at_utc DESC LIMIT 1) AS active_mission_id,
                    (SELECT m.status FROM missions m WHERE m.vehicle_id = s.vehicle_id ORDER BY m.created_at_utc DESC LIMIT 1) AS latest_mission_status
                FROM sensors s
                {where}
                ORDER BY s.vehicle_id, s.sensor_id
                """,
                params,
            ).fetchall()
        return [self._decode_sensor(row) for row in rows]

    def update_sensor(
        self, sensor_id: str, request: SensorUpdate
    ) -> dict[str, Any] | None:
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return self.get_sensor(sensor_id)
        mapping = {
            "sensor_name": "sensor_name",
            "sensor_type": "sensor_type",
            "manufacturer": "manufacturer",
            "model": "model",
            "unit": "unit",
            "sampling_rate_hz": "sampling_rate_hz",
            "coordinate_frame": "coordinate_frame",
            "enabled": "enabled",
            "metadata": "metadata_json",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{mapping[key]} = ?")
            if key == "enabled":
                value = 1 if value else 0
            elif key == "metadata":
                value = json.dumps(value, separators=(",", ":"))
            params.append(value)
        assignments.append("updated_at_utc = ?")
        params.append(self._utc_now().isoformat())
        params.append(sensor_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE sensors SET {', '.join(assignments)} WHERE sensor_id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None
        return self.get_sensor(sensor_id)

    def delete_sensor(self, sensor_id: str) -> bool:
        with self._lock, self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS total FROM raw_sensor_messages WHERE sensor_id = ?",
                (sensor_id,),
            ).fetchone()
            if count and int(count["total"]) > 0:
                raise ValueError("Sensor has stored messages; disable it instead")
            cursor = connection.execute(
                "DELETE FROM sensors WHERE sensor_id = ?", (sensor_id,)
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Vehicle heartbeat
    # ------------------------------------------------------------------
    def insert_heartbeat(
        self,
        heartbeat: VehicleHeartbeat,
        transport: TransportType = "HTTP",
    ) -> dict[str, Any]:
        self.ensure_vehicle(heartbeat.vehicle_id)
        if heartbeat.mission_id:
            mission = self.get_mission(heartbeat.mission_id)
            if mission is None:
                raise LookupError("Mission not found")
            if mission["vehicle_id"] != heartbeat.vehicle_id:
                raise ValueError("Heartbeat mission_id does not belong to the vehicle")
        received_at = self._utc_now()
        latency_ms = max(
            0.0, (received_at - heartbeat.timestamp_utc).total_seconds() * 1000.0
        )
        record = heartbeat.model_dump(mode="json")
        record.update(
            {
                "received_at_utc": received_at.isoformat(),
                "latency_ms": round(latency_ms, 3),
                "transport": transport,
            }
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicle_heartbeats (
                    message_id, vehicle_id, mission_id, timestamp_utc, received_at_utc,
                    state, transport, source, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(heartbeat.message_id),
                    heartbeat.vehicle_id,
                    heartbeat.mission_id,
                    heartbeat.timestamp_utc.isoformat(),
                    received_at.isoformat(),
                    heartbeat.state,
                    transport,
                    heartbeat.source,
                    json.dumps(heartbeat.metadata, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                UPDATE vehicles SET updated_at_utc = ? WHERE vehicle_id = ?
                """,
                (received_at.isoformat(), heartbeat.vehicle_id),
            )
        return record

    def heartbeat_history(
        self, vehicle_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM vehicle_heartbeats
                WHERE vehicle_id = ?
                ORDER BY received_at_utc DESC, id DESC
                LIMIT ?
                """,
                (vehicle_id, limit),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = self._load_json(item.pop("metadata_json", "{}"))
            item.pop("id", None)
            records.append(item)
        return records

    # ------------------------------------------------------------------
    # Mission catalogue
    # ------------------------------------------------------------------
    def create_mission(self, request: MissionCreate) -> dict[str, Any]:
        self.ensure_vehicle(request.vehicle_id)
        now = self._utc_now().isoformat()
        mission_id = request.mission_id or self._generated_id("MISSION")
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO missions (
                    mission_id, vehicle_id, name, scenario_name, status,
                    description, metadata_json, created_at_utc
                ) VALUES (?, ?, ?, ?, 'PLANNED', ?, ?, ?)
                """,
                (
                    mission_id,
                    request.vehicle_id,
                    request.name,
                    request.scenario_name,
                    request.description,
                    json.dumps(request.metadata, separators=(",", ":")),
                    now,
                ),
            )
        mission = self.get_mission(mission_id)
        if mission is None:
            raise RuntimeError("Mission was not created")
        return mission

    def ensure_mission(
        self,
        mission_id: str,
        vehicle_id: str,
        timestamp_utc: datetime,
    ) -> None:
        self.ensure_vehicle(vehicle_id)
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO missions (
                    mission_id, vehicle_id, name, scenario_name, status,
                    description, metadata_json, created_at_utc, started_at_utc
                ) VALUES (?, ?, ?, NULL, 'RUNNING', '', '{}', ?, ?)
                """,
                (
                    mission_id,
                    vehicle_id,
                    f"Auto-created mission {mission_id}",
                    now,
                    timestamp_utc.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT vehicle_id FROM missions WHERE mission_id = ?", (mission_id,)
            ).fetchone()
            if row and row["vehicle_id"] != vehicle_id:
                raise ValueError(
                    f"Mission {mission_id} belongs to vehicle {row['vehicle_id']}"
                )
            connection.execute(
                """
                UPDATE missions
                SET status = CASE WHEN status = 'PLANNED' THEN 'RUNNING' ELSE status END,
                    started_at_utc = COALESCE(started_at_utc, ?)
                WHERE mission_id = ?
                """,
                (timestamp_utc.isoformat(), mission_id),
            )

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT m.*,
                    (SELECT COUNT(*) FROM telemetry t WHERE t.mission_id = m.mission_id) AS telemetry_count,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.mission_id = m.mission_id) AS raw_message_count,
                    (SELECT COUNT(*) FROM mission_events e WHERE e.mission_id = m.mission_id) AS event_count,
                    (SELECT MAX(t.timestamp_utc) FROM telemetry t WHERE t.mission_id = m.mission_id) AS latest_timestamp_utc
                FROM missions m WHERE m.mission_id = ?
                """,
                (mission_id,),
            ).fetchone()
        return self._decode_mission(row) if row else None

    def list_missions(
        self,
        vehicle_id: str | None = None,
        status: MissionStatus | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if vehicle_id:
            where.append("m.vehicle_id = ?")
            params.append(vehicle_id)
        if status:
            where.append("m.status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*,
                    (SELECT COUNT(*) FROM telemetry t WHERE t.mission_id = m.mission_id) AS telemetry_count,
                    (SELECT COUNT(*) FROM raw_sensor_messages r WHERE r.mission_id = m.mission_id) AS raw_message_count,
                    (SELECT COUNT(*) FROM mission_events e WHERE e.mission_id = m.mission_id) AS event_count,
                    (SELECT MAX(t.timestamp_utc) FROM telemetry t WHERE t.mission_id = m.mission_id) AS latest_timestamp_utc
                FROM missions m
                {where_sql}
                ORDER BY m.created_at_utc DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._decode_mission(row) for row in rows]

    def transition_mission(
        self, mission_id: str, target: MissionStatus
    ) -> dict[str, Any] | None:
        allowed: dict[str, set[str]] = {
            "PLANNED": {"RUNNING", "ABORTED"},
            "RUNNING": {"COMPLETED", "ABORTED"},
            "COMPLETED": set(),
            "ABORTED": set(),
        }
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM missions WHERE mission_id = ?", (mission_id,)
            ).fetchone()
            if row is None:
                return None
            current = str(row["status"])
            if target != current:
                if target not in allowed[current]:
                    raise ValueError(
                        f"Mission cannot transition from {current} to {target}"
                    )
                now = self._utc_now().isoformat()
                started = now if target == "RUNNING" else None
                ended = now if target in {"COMPLETED", "ABORTED"} else None
                connection.execute(
                    """
                    UPDATE missions
                    SET status = ?, started_at_utc = COALESCE(started_at_utc, ?),
                        ended_at_utc = COALESCE(?, ended_at_utc)
                    WHERE mission_id = ?
                    """,
                    (target, started, ended, mission_id),
                )
        return self.get_mission(mission_id)

    # ------------------------------------------------------------------
    # Normalised telemetry and raw acquisition
    # ------------------------------------------------------------------
    def insert_telemetry(self, frame: TelemetryFrame) -> dict[str, Any]:
        self.ensure_mission(frame.mission_id, frame.vehicle_id, frame.timestamp_utc)
        received_at = self._utc_now()
        latency_ms = max(
            0.0, (received_at - frame.timestamp_utc).total_seconds() * 1000.0
        )
        payload = frame.model_dump(mode="json")
        payload["received_at_utc"] = received_at.isoformat()
        payload["latency_ms"] = round(latency_ms, 3)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO telemetry (
                    message_id, vehicle_id, mission_id, sequence_no,
                    timestamp_utc, received_at_utc, latency_ms,
                    x_m, y_m, z_m, speed_mps, battery_percent,
                    operating_mode, valid, confidence, source,
                    coordinate_frame, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(frame.message_id),
                    frame.vehicle_id,
                    frame.mission_id,
                    frame.sequence_no,
                    frame.timestamp_utc.isoformat(),
                    received_at.isoformat(),
                    latency_ms,
                    frame.position.x_m,
                    frame.position.y_m,
                    frame.position.z_m,
                    frame.velocity.speed_mps,
                    frame.state.battery_percent,
                    frame.state.operating_mode,
                    1 if frame.quality.valid else 0,
                    frame.quality.confidence,
                    frame.source,
                    frame.coordinate_frame,
                    json.dumps(payload, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                UPDATE vehicles SET last_seen_at_utc = ?, updated_at_utc = ?
                WHERE vehicle_id = ?
                """,
                (received_at.isoformat(), received_at.isoformat(), frame.vehicle_id),
            )
        return payload

    def insert_raw_message(
        self,
        message: RawSensorMessage,
        transport: TransportType = "HTTP",
        topic: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_sensor(message)
        self.ensure_mission(
            message.mission_id, message.vehicle_id, message.timestamp_utc
        )
        received_at = self._utc_now()
        latency_ms = max(
            0.0, (received_at - message.timestamp_utc).total_seconds() * 1000.0
        )
        record = message.model_dump(mode="json")
        record.update(
            {
                "received_at_utc": received_at.isoformat(),
                "latency_ms": round(latency_ms, 3),
                "transport": transport,
                "topic": topic,
            }
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO raw_sensor_messages (
                    message_id, vehicle_id, sensor_id, mission_id, sequence_no,
                    timestamp_utc, received_at_utc, latency_ms, message_type,
                    transport, topic, valid, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(message.message_id),
                    message.vehicle_id,
                    message.sensor_id,
                    message.mission_id,
                    message.sequence_no,
                    message.timestamp_utc.isoformat(),
                    received_at.isoformat(),
                    latency_ms,
                    message.message_type,
                    transport,
                    topic,
                    1 if message.quality.valid else 0,
                    message.quality.confidence,
                    json.dumps(record, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                UPDATE sensors
                SET last_seen_at_utc = ?, last_transport = ?,
                    message_count = message_count + 1,
                    invalid_message_count = invalid_message_count + ?,
                    updated_at_utc = ?
                WHERE sensor_id = ?
                """,
                (
                    received_at.isoformat(),
                    transport,
                    0 if message.quality.valid else 1,
                    received_at.isoformat(),
                    message.sensor_id,
                ),
            )
            connection.execute(
                """
                UPDATE vehicles SET last_seen_at_utc = ?, updated_at_utc = ?
                WHERE vehicle_id = ?
                """,
                (received_at.isoformat(), received_at.isoformat(), message.vehicle_id),
            )
        return record

    def latest(self, vehicle_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM telemetry WHERE vehicle_id = ?
                ORDER BY timestamp_utc DESC, id DESC LIMIT 1
                """,
                (vehicle_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def history(
        self, vehicle_id: str, mission_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        if mission_id:
            sql = """
                SELECT payload_json FROM telemetry
                WHERE vehicle_id = ? AND mission_id = ?
                ORDER BY timestamp_utc DESC, id DESC LIMIT ?
            """
            params: tuple[Any, ...] = (vehicle_id, mission_id, limit)
        else:
            sql = """
                SELECT payload_json FROM telemetry WHERE vehicle_id = ?
                ORDER BY timestamp_utc DESC, id DESC LIMIT ?
            """
            params = (vehicle_id, limit)
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        records = [json.loads(row["payload_json"]) for row in rows]
        records.reverse()
        return records

    def mission_history(
        self, mission_id: str, limit: int = 100_000
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM telemetry WHERE mission_id = ?
                ORDER BY timestamp_utc ASC, id ASC LIMIT ?
                """,
                (mission_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def raw_history(
        self,
        vehicle_id: str | None = None,
        sensor_id: str | None = None,
        mission_id: str | None = None,
        message_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("vehicle_id", vehicle_id),
            ("sensor_id", sensor_id),
            ("mission_id", mission_id),
            ("message_type", message_type),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json FROM raw_sensor_messages
                {where_sql}
                ORDER BY timestamp_utc DESC, id DESC LIMIT ?
                """,
                params,
            ).fetchall()
        records = [json.loads(row["payload_json"]) for row in rows]
        records.reverse()
        return records

    def sensor_quality_summary(
        self, sensor_id: str, mission_id: str | None = None
    ) -> dict[str, Any] | None:
        if self.get_sensor(sensor_id) is None:
            return None
        where = "sensor_id = ?"
        params: list[Any] = [sensor_id]
        if mission_id:
            where += " AND mission_id = ?"
            params.append(mission_id)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT sequence_no, timestamp_utc, latency_ms, valid, confidence, transport
                FROM raw_sensor_messages WHERE {where}
                ORDER BY timestamp_utc ASC, id ASC
                """,
                params,
            ).fetchall()
        return self._quality_from_rows(
            rows, {"sensor_id": sensor_id, "mission_id": mission_id}
        )

    def quality_summary(self, mission_id: str) -> dict[str, Any] | None:
        if self.get_mission(mission_id) is None:
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence_no, timestamp_utc, latency_ms, valid, confidence
                FROM telemetry WHERE mission_id = ?
                ORDER BY timestamp_utc ASC, id ASC
                """,
                (mission_id,),
            ).fetchall()
        return self._quality_from_rows(rows, {"mission_id": mission_id})

    @staticmethod
    def _quality_from_rows(
        rows: list[sqlite3.Row], identity: dict[str, Any]
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            **identity,
            "message_count": len(rows),
            "telemetry_count": len(rows),
            "first_sequence_no": None,
            "last_sequence_no": None,
            "missing_frames": 0,
            "out_of_order_frames": 0,
            "invalid_frames": 0,
            "average_confidence": None,
            "average_rate_hz": None,
            "average_latency_ms": None,
            "maximum_latency_ms": None,
            "duration_s": None,
        }
        if not rows:
            return result
        sequences = [int(row["sequence_no"]) for row in rows]
        missing = 0
        out_of_order = 0
        highest = sequences[0]
        seen: set[int] = set()
        for sequence in sequences:
            if sequence in seen or sequence < highest:
                out_of_order += 1
            if sequence > highest + 1:
                missing += sequence - highest - 1
            highest = max(highest, sequence)
            seen.add(sequence)
        first_time = datetime.fromisoformat(rows[0]["timestamp_utc"])
        last_time = datetime.fromisoformat(rows[-1]["timestamp_utc"])
        duration_s = max(0.0, (last_time - first_time).total_seconds())
        rate_hz = (
            (len(rows) - 1) / duration_s if len(rows) > 1 and duration_s > 0 else None
        )
        latencies = [float(row["latency_ms"]) for row in rows]
        confidences = [float(row["confidence"]) for row in rows]
        result.update(
            {
                "first_sequence_no": min(sequences),
                "last_sequence_no": max(sequences),
                "missing_frames": missing,
                "out_of_order_frames": out_of_order,
                "invalid_frames": sum(1 for row in rows if not bool(row["valid"])),
                "average_confidence": round(sum(confidences) / len(confidences), 6),
                "average_rate_hz": round(rate_hz, 4) if rate_hz is not None else None,
                "average_latency_ms": round(sum(latencies) / len(latencies), 3),
                "maximum_latency_ms": round(max(latencies), 3),
                "duration_s": round(duration_s, 3),
            }
        )
        return result

    # ------------------------------------------------------------------
    # Data-integrity state, events and alerts
    # ------------------------------------------------------------------
    def raw_integrity_state(
        self,
        mission_id: str,
        sensor_id: str,
        message_id: str,
        sequence_no: int,
        rate_window_s: float = 10.0,
    ) -> dict[str, Any]:
        cutoff = (
            self._utc_now() - timedelta(seconds=max(1.0, rate_window_s))
        ).isoformat()
        with self._connect() as connection:
            message_exists = (
                connection.execute(
                    "SELECT 1 FROM raw_sensor_messages WHERE message_id = ? LIMIT 1",
                    (message_id,),
                ).fetchone()
                is not None
            )
            sequence_exists = (
                connection.execute(
                    """
                SELECT 1 FROM raw_sensor_messages
                WHERE mission_id = ? AND sensor_id = ? AND sequence_no = ?
                LIMIT 1
                """,
                    (mission_id, sensor_id, sequence_no),
                ).fetchone()
                is not None
            )
            aggregate = connection.execute(
                """
                SELECT MAX(sequence_no) AS max_sequence
                FROM raw_sensor_messages
                WHERE mission_id = ? AND sensor_id = ?
                """,
                (mission_id, sensor_id),
            ).fetchone()
            latest = connection.execute(
                """
                SELECT timestamp_utc, received_at_utc, latency_ms
                FROM raw_sensor_messages
                WHERE mission_id = ? AND sensor_id = ?
                ORDER BY received_at_utc DESC, id DESC LIMIT 1
                """,
                (mission_id, sensor_id),
            ).fetchone()
            recent = connection.execute(
                """
                SELECT received_at_utc FROM raw_sensor_messages
                WHERE mission_id = ? AND sensor_id = ? AND received_at_utc >= ?
                ORDER BY received_at_utc ASC, id ASC
                """,
                (mission_id, sensor_id, cutoff),
            ).fetchall()
            sensor = connection.execute(
                "SELECT sampling_rate_hz FROM sensors WHERE sensor_id = ?",
                (sensor_id,),
            ).fetchone()
        return {
            "message_id_exists": message_exists,
            "sequence_exists": sequence_exists,
            "max_sequence": (
                int(aggregate["max_sequence"])
                if aggregate and aggregate["max_sequence"] is not None
                else None
            ),
            "latest_timestamp_utc": latest["timestamp_utc"] if latest else None,
            "previous_received_at_utc": latest["received_at_utc"] if latest else None,
            "previous_latency_ms": float(latest["latency_ms"]) if latest else None,
            "expected_rate_hz": (
                float(sensor["sampling_rate_hz"])
                if sensor and sensor["sampling_rate_hz"] is not None
                else None
            ),
            "recent_received_at_utc": [str(row["received_at_utc"]) for row in recent],
        }

    def telemetry_integrity_state(
        self, mission_id: str, vehicle_id: str, message_id: str, sequence_no: int
    ) -> dict[str, Any]:
        with self._connect() as connection:
            message_exists = (
                connection.execute(
                    "SELECT 1 FROM telemetry WHERE message_id = ? LIMIT 1",
                    (message_id,),
                ).fetchone()
                is not None
            )
            sequence_exists = (
                connection.execute(
                    """
                SELECT 1 FROM telemetry
                WHERE mission_id = ? AND vehicle_id = ? AND sequence_no = ?
                LIMIT 1
                """,
                    (mission_id, vehicle_id, sequence_no),
                ).fetchone()
                is not None
            )
            aggregate = connection.execute(
                """
                SELECT MAX(sequence_no) AS max_sequence
                FROM telemetry
                WHERE mission_id = ? AND vehicle_id = ?
                """,
                (mission_id, vehicle_id),
            ).fetchone()
            latest = connection.execute(
                """
                SELECT timestamp_utc, received_at_utc, latency_ms
                FROM telemetry
                WHERE mission_id = ? AND vehicle_id = ?
                ORDER BY received_at_utc DESC, id DESC LIMIT 1
                """,
                (mission_id, vehicle_id),
            ).fetchone()
        return {
            "message_id_exists": message_exists,
            "sequence_exists": sequence_exists,
            "max_sequence": (
                int(aggregate["max_sequence"])
                if aggregate and aggregate["max_sequence"] is not None
                else None
            ),
            "latest_timestamp_utc": latest["timestamp_utc"] if latest else None,
            "previous_received_at_utc": latest["received_at_utc"] if latest else None,
            "previous_latency_ms": float(latest["latency_ms"]) if latest else None,
        }

    def record_integrity_findings(
        self, findings: list[IntegrityFinding]
    ) -> dict[str, list[dict[str, Any]]]:
        if not findings:
            return {"integrity_events": [], "alerts": []}
        created_events: list[dict[str, Any]] = []
        touched_alert_ids: list[str] = []
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            for finding in findings:
                integrity_event_id = self._generated_id("INTEGRITY")
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO integrity_events (
                        integrity_event_id, dedup_key, stream_kind, check_type, severity,
                        vehicle_id, sensor_id, mission_id, message_id, sequence_no,
                        detected_at_utc, description, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        integrity_event_id,
                        finding.dedup_key,
                        finding.stream_kind,
                        finding.check_type,
                        finding.severity,
                        finding.vehicle_id,
                        finding.sensor_id,
                        finding.mission_id,
                        finding.message_id,
                        finding.sequence_no,
                        now,
                        finding.description,
                        json.dumps(finding.details, separators=(",", ":")),
                    ),
                )
                if cursor.rowcount == 0:
                    continue
                row = connection.execute(
                    "SELECT * FROM integrity_events WHERE integrity_event_id = ?",
                    (integrity_event_id,),
                ).fetchone()
                if row is not None:
                    created_events.append(self._decode_integrity_event(row))

                existing = connection.execute(
                    "SELECT * FROM alerts WHERE active_key = ?",
                    (finding.alert_active_key,),
                ).fetchone()
                alert_metadata = {
                    "latest_integrity_event_id": integrity_event_id,
                    "latest_message_id": finding.message_id,
                    "latest_sequence_no": finding.sequence_no,
                    "stream_kind": finding.stream_kind,
                    "latest_details": finding.details,
                }
                if existing is None:
                    alert_id = self._generated_id("ALERT")
                    connection.execute(
                        """
                        INSERT INTO alerts (
                            alert_id, active_key, integrity_event_id, alert_type, severity, status,
                            vehicle_id, sensor_id, mission_id, title, description,
                            first_detected_at_utc, last_detected_at_utc, occurrence_count,
                            metadata_json
                        ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            alert_id,
                            finding.alert_active_key,
                            integrity_event_id,
                            finding.alert_type,
                            finding.severity,
                            finding.vehicle_id,
                            finding.sensor_id,
                            finding.mission_id,
                            finding.alert_title,
                            finding.description,
                            now,
                            now,
                            json.dumps(alert_metadata, separators=(",", ":")),
                        ),
                    )
                else:
                    alert_id = str(existing["alert_id"])
                    current_severity = str(existing["severity"])
                    severity_order = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}
                    severity = (
                        finding.severity
                        if severity_order.get(finding.severity, 0)
                        > severity_order.get(current_severity, 0)
                        else current_severity
                    )
                    connection.execute(
                        """
                        UPDATE alerts
                        SET integrity_event_id = ?, severity = ?, title = ?, description = ?,
                            last_detected_at_utc = ?, occurrence_count = occurrence_count + 1,
                            metadata_json = ?
                        WHERE alert_id = ?
                        """,
                        (
                            integrity_event_id,
                            severity,
                            finding.alert_title,
                            finding.description,
                            now,
                            json.dumps(alert_metadata, separators=(",", ":")),
                            alert_id,
                        ),
                    )
                touched_alert_ids.append(alert_id)

            alerts: list[dict[str, Any]] = []
            for alert_id in dict.fromkeys(touched_alert_ids):
                row = connection.execute(
                    "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)
                ).fetchone()
                if row is not None:
                    alerts.append(self._decode_alert(row))
        return {"integrity_events": created_events, "alerts": alerts}

    def auto_resolve_recovered_alerts(
        self,
        *,
        mission_id: str,
        sensor_id: str | None,
        evaluated_types: set[str],
        active_types: set[str],
    ) -> list[dict[str, Any]]:
        """Automatically resolve recoverable alerts that were evaluated healthy.

        Only alert types explicitly evaluated for the current message are
        considered. This prevents startup windows or missing rate context from
        resolving an alert prematurely.
        """
        recovered = sorted(set(evaluated_types) - set(active_types))
        if not recovered:
            return []
        placeholders = ",".join("?" for _ in recovered)
        sensor_clause = "sensor_id IS NULL" if sensor_id is None else "sensor_id = ?"
        params: list[Any] = [mission_id, *recovered]
        if sensor_id is not None:
            params.append(sensor_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT alert_id, alert_type FROM alerts
                WHERE mission_id = ?
                  AND alert_type IN ({placeholders})
                  AND {sensor_clause}
                  AND status != 'RESOLVED'
                """,
                params,
            ).fetchall()
            if not rows:
                return []
            now = self._utc_now().isoformat()
            resolved_ids: list[str] = []
            for row in rows:
                alert_id = str(row["alert_id"])
                alert_type = str(row["alert_type"])
                connection.execute(
                    """
                    UPDATE alerts
                    SET status = 'RESOLVED', active_key = NULL,
                        resolved_at_utc = ?, resolved_by = 'system',
                        resolution_source = 'AUTOMATIC',
                        resolution_reason = ?, operator_note = ?
                    WHERE alert_id = ?
                    """,
                    (
                        now,
                        f"{alert_type} condition returned to the configured healthy range.",
                        "Automatically resolved by the v0.4.1 integrity engine.",
                        alert_id,
                    ),
                )
                resolved_ids.append(alert_id)
            resolved: list[dict[str, Any]] = []
            for alert_id in resolved_ids:
                row = connection.execute(
                    "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)
                ).fetchone()
                if row is not None:
                    resolved.append(self._decode_alert(row))
            return resolved

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        rank = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = rank - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction

    def sensor_integrity_metrics(
        self, sensor_id: str, mission_id: str | None = None
    ) -> dict[str, Any] | None:
        sensor = self.get_sensor(sensor_id)
        if sensor is None:
            return None
        where = ["sensor_id = ?"]
        params: list[Any] = [sensor_id]
        if mission_id:
            where.append("mission_id = ?")
            params.append(mission_id)
        where_sql = " AND ".join(where)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT mission_id, sequence_no, timestamp_utc, received_at_utc,
                       latency_ms, valid, confidence
                FROM raw_sensor_messages
                WHERE {where_sql}
                ORDER BY received_at_utc ASC, id ASC
                """,
                params,
            ).fetchall()
            event_rows = connection.execute(
                f"""
                SELECT check_type, details_json, COUNT(*) AS event_count
                FROM integrity_events
                WHERE sensor_id = ? {"AND mission_id = ?" if mission_id else ""}
                GROUP BY check_type, details_json
                """,
                [sensor_id, mission_id] if mission_id else [sensor_id],
            ).fetchall()
            alert_rows = connection.execute(
                f"""
                SELECT severity, status, COUNT(*) AS count
                FROM alerts
                WHERE sensor_id = ? {"AND mission_id = ?" if mission_id else ""}
                GROUP BY severity, status
                """,
                [sensor_id, mission_id] if mission_id else [sensor_id],
            ).fetchall()

        expected_rate = sensor.get("sampling_rate_hz")
        received = len(rows)
        actual_rate: float | None = None
        duration_s: float | None = None
        if len(rows) > 1:
            first_received = datetime.fromisoformat(str(rows[0]["received_at_utc"]))
            last_received = datetime.fromisoformat(str(rows[-1]["received_at_utc"]))
            duration_s = max(0.0, (last_received - first_received).total_seconds())
            if duration_s > 0:
                actual_rate = (len(rows) - 1) / duration_s

        latencies = [float(row["latency_ms"]) for row in rows]
        check_counts: dict[str, int] = {}
        missing_messages = 0
        for row in event_rows:
            check_type = str(row["check_type"])
            check_counts[check_type] = check_counts.get(check_type, 0) + int(
                row["event_count"]
            )
            if check_type == "SEQUENCE_GAP":
                details = self._load_json(str(row["details_json"]))
                missing_messages += int(details.get("missing_count", 0) or 0) * int(
                    row["event_count"]
                )

        open_critical = 0
        open_warning = 0
        alerts_by_status: dict[str, int] = {}
        for row in alert_rows:
            status = str(row["status"])
            count = int(row["count"])
            alerts_by_status[status] = alerts_by_status.get(status, 0) + count
            if status != "RESOLVED" and str(row["severity"]) == "CRITICAL":
                open_critical += count
            elif status != "RESOLVED":
                open_warning += count
        if received == 0:
            health = "NO_DATA"
        elif open_critical:
            health = "CRITICAL"
        elif open_warning:
            health = "WARNING"
        else:
            health = "HEALTHY"

        mission_values = sorted({str(row["mission_id"]) for row in rows})
        return {
            "sensor_id": sensor_id,
            "vehicle_id": sensor["vehicle_id"],
            "mission_id": mission_id,
            "missions": mission_values,
            "health_status": health,
            "expected_rate_hz": (
                round(float(expected_rate), 4) if expected_rate is not None else None
            ),
            "actual_rate_hz": (
                round(actual_rate, 4) if actual_rate is not None else None
            ),
            "rate_ratio": (
                round(actual_rate / float(expected_rate), 4)
                if actual_rate is not None and expected_rate not in (None, 0)
                else None
            ),
            "received_messages": received,
            "missing_messages": missing_messages,
            "duplicate_messages": check_counts.get("DUPLICATE_MESSAGE", 0),
            "out_of_order_messages": check_counts.get("OUT_OF_ORDER", 0),
            "timestamp_regressions": check_counts.get("TIMESTAMP_REGRESSION", 0),
            "future_timestamps": check_counts.get("FUTURE_TIMESTAMP", 0),
            "low_rate_events": check_counts.get("LOW_SAMPLING_RATE", 0),
            "high_rate_events": check_counts.get("HIGH_SAMPLING_RATE", 0),
            "high_latency_events": check_counts.get("HIGH_LATENCY", 0),
            "clock_drift_events": check_counts.get("CLOCK_DRIFT", 0),
            "invalid_messages": sum(1 for row in rows if not bool(row["valid"])),
            "average_latency_ms": (
                round(sum(latencies) / len(latencies), 3) if latencies else None
            ),
            "p50_latency_ms": (
                round(value, 3)
                if (value := self._percentile(latencies, 0.50)) is not None
                else None
            ),
            "p95_latency_ms": (
                round(value, 3)
                if (value := self._percentile(latencies, 0.95)) is not None
                else None
            ),
            "maximum_latency_ms": round(max(latencies), 3) if latencies else None,
            "duration_s": round(duration_s, 3) if duration_s is not None else None,
            "integrity_events_by_type": check_counts,
            "alerts_by_status": alerts_by_status,
        }

    def mission_integrity_metrics(self, mission_id: str) -> dict[str, Any] | None:
        mission = self.get_mission(mission_id)
        if mission is None:
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT sensor_id FROM raw_sensor_messages
                WHERE mission_id = ? ORDER BY sensor_id
                """,
                (mission_id,),
            ).fetchall()
        sensors = [
            metric
            for row in rows
            if (
                metric := self.sensor_integrity_metrics(
                    str(row["sensor_id"]), mission_id
                )
            )
            is not None
        ]
        total_received = sum(int(item["received_messages"]) for item in sensors)
        total_missing = sum(int(item["missing_messages"]) for item in sensors)
        weighted_latency_numerator = sum(
            float(item["average_latency_ms"] or 0.0) * int(item["received_messages"])
            for item in sensors
        )
        return {
            "mission_id": mission_id,
            "vehicle_id": mission["vehicle_id"],
            "sensor_count": len(sensors),
            "sensors": sensors,
            "summary": {
                "received_messages": total_received,
                "missing_messages": total_missing,
                "duplicate_messages": sum(
                    int(item["duplicate_messages"]) for item in sensors
                ),
                "out_of_order_messages": sum(
                    int(item["out_of_order_messages"]) for item in sensors
                ),
                "invalid_messages": sum(
                    int(item["invalid_messages"]) for item in sensors
                ),
                "average_latency_ms": (
                    round(weighted_latency_numerator / total_received, 3)
                    if total_received
                    else None
                ),
                "critical_sensors": sum(
                    1 for item in sensors if item["health_status"] == "CRITICAL"
                ),
                "warning_sensors": sum(
                    1 for item in sensors if item["health_status"] == "WARNING"
                ),
                "healthy_sensors": sum(
                    1 for item in sensors if item["health_status"] == "HEALTHY"
                ),
            },
        }

    def get_integrity_event(self, integrity_event_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM integrity_events WHERE integrity_event_id = ?",
                (integrity_event_id,),
            ).fetchone()
        return self._decode_integrity_event(row) if row else None

    def list_integrity_events(
        self,
        vehicle_id: str | None = None,
        sensor_id: str | None = None,
        mission_id: str | None = None,
        check_type: str | None = None,
        severity: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("vehicle_id", vehicle_id),
            ("sensor_id", sensor_id),
            ("mission_id", mission_id),
            ("check_type", check_type),
            ("severity", severity),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM integrity_events {where_sql}
                ORDER BY detected_at_utc DESC, integrity_event_id DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._decode_integrity_event(row) for row in rows]

    def integrity_summary(self, mission_id: str) -> dict[str, Any] | None:
        if self.get_mission(mission_id) is None:
            return None
        with self._connect() as connection:
            event_rows = connection.execute(
                """
                SELECT check_type, COUNT(*) AS count
                FROM integrity_events WHERE mission_id = ? GROUP BY check_type
                """,
                (mission_id,),
            ).fetchall()
            severity_rows = connection.execute(
                """
                SELECT severity, COUNT(*) AS count
                FROM integrity_events WHERE mission_id = ? GROUP BY severity
                """,
                (mission_id,),
            ).fetchall()
            alert_rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM alerts WHERE mission_id = ? GROUP BY status
                """,
                (mission_id,),
            ).fetchall()
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM integrity_events WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()["count"]
        return {
            "mission_id": mission_id,
            "integrity_event_count": int(total),
            "by_check_type": {
                str(row["check_type"]): int(row["count"]) for row in event_rows
            },
            "by_severity": {
                str(row["severity"]): int(row["count"]) for row in severity_rows
            },
            "alerts_by_status": {
                str(row["status"]): int(row["count"]) for row in alert_rows
            },
        }

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        return self._decode_alert(row) if row else None

    def list_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        vehicle_id: str | None = None,
        sensor_id: str | None = None,
        mission_id: str | None = None,
        alert_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("status", status),
            ("severity", severity),
            ("vehicle_id", vehicle_id),
            ("sensor_id", sensor_id),
            ("mission_id", mission_id),
            ("alert_type", alert_type),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM alerts {where_sql}
                ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                         last_detected_at_utc DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._decode_alert(row) for row in rows]

    def acknowledge_alert(
        self, alert_id: str, actor: str, note: str = ""
    ) -> dict[str, Any] | None:
        current = self.get_alert(alert_id)
        if current is None:
            return None
        if current["status"] == "RESOLVED":
            raise ValueError("Resolved alerts cannot be acknowledged")
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE alerts SET status = 'ACKNOWLEDGED', acknowledged_at_utc = ?,
                    acknowledged_by = ?, operator_note = ? WHERE alert_id = ?
                """,
                (now, actor, note, alert_id),
            )
        return self.get_alert(alert_id)

    def resolve_alert(
        self, alert_id: str, actor: str, note: str = ""
    ) -> dict[str, Any] | None:
        current = self.get_alert(alert_id)
        if current is None:
            return None
        if current["status"] == "RESOLVED":
            return current
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE alerts SET status = 'RESOLVED', active_key = NULL,
                    resolved_at_utc = ?, resolved_by = ?,
                    resolution_source = 'MANUAL', resolution_reason = ?,
                    operator_note = ?
                WHERE alert_id = ?
                """,
                (
                    now,
                    actor,
                    note or "Manually resolved by an operator.",
                    note,
                    alert_id,
                ),
            )
        return self.get_alert(alert_id)

    # ------------------------------------------------------------------
    # Operational monitoring, logs and platform alerts
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_application_log(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["details"] = json.loads(record.pop("details_json") or "{}")
        return record

    @staticmethod
    def _decode_system_snapshot(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["details"] = json.loads(record.pop("details_json") or "{}")
        return record

    @staticmethod
    def _decode_platform_alert(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = json.loads(record.pop("metadata_json") or "{}")
        return record

    def create_application_log(
        self,
        *,
        level: str,
        component: str,
        event_type: str,
        message: str,
        vehicle_id: str | None = None,
        sensor_id: str | None = None,
        mission_id: str | None = None,
        details: dict[str, Any] | None = None,
        timestamp_utc: datetime | None = None,
    ) -> dict[str, Any]:
        log_id = self._generated_id("LOG")
        timestamp = (
            (timestamp_utc or self._utc_now()).astimezone(timezone.utc).isoformat()
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO application_logs (
                    log_id, timestamp_utc, level, component, event_type, message,
                    vehicle_id, sensor_id, mission_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    timestamp,
                    level,
                    component,
                    event_type,
                    message,
                    vehicle_id,
                    sensor_id,
                    mission_id,
                    json.dumps(details or {}, separators=(",", ":")),
                ),
            )
        created = self.get_application_log(log_id)
        if created is None:
            raise RuntimeError("Application log was not created")
        return created

    def get_application_log(self, log_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM application_logs WHERE log_id = ?", (log_id,)
            ).fetchone()
        return self._decode_application_log(row) if row else None

    def list_application_logs(
        self,
        *,
        level: str | None = None,
        component: str | None = None,
        event_type: str | None = None,
        vehicle_id: str | None = None,
        sensor_id: str | None = None,
        mission_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("level", level),
            ("component", component),
            ("event_type", event_type),
            ("vehicle_id", vehicle_id),
            ("sensor_id", sensor_id),
            ("mission_id", mission_id),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        if start_time:
            where.append("timestamp_utc >= ?")
            params.append(start_time)
        if end_time:
            where.append("timestamp_utc <= ?")
            params.append(end_time)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM application_logs {where_sql}
                ORDER BY timestamp_utc DESC, log_id DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._decode_application_log(row) for row in rows]

    def create_system_metric_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        snapshot_id = self._generated_id("METRIC")
        runtime = snapshot.get("runtime", {})
        rates = runtime.get("rates", {})
        database = runtime.get("database", {})
        process = runtime.get("process", {})
        operations = snapshot.get("operations", {})
        timestamp = snapshot.get("captured_at_utc") or self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_metric_snapshots (
                    snapshot_id, timestamp_utc, overall_status, uptime_seconds,
                    raw_rate_per_second, telemetry_rate_per_second,
                    http_rate_per_second, mqtt_rate_per_second,
                    database_write_latency_ms, database_query_latency_ms,
                    websocket_clients, memory_usage_mb, cpu_percent,
                    open_alerts, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    timestamp,
                    snapshot.get("overall_status", "UNKNOWN"),
                    float(snapshot.get("uptime_seconds", 0.0)),
                    float(
                        rates.get("raw_messages_received", {}).get(
                            "one_minute_per_second", 0.0
                        )
                    ),
                    float(
                        rates.get("telemetry_frames_received", {}).get(
                            "one_minute_per_second", 0.0
                        )
                    ),
                    float(
                        rates.get("http_messages_received", {}).get(
                            "one_minute_per_second", 0.0
                        )
                    ),
                    float(
                        rates.get("mqtt_messages_received", {}).get(
                            "one_minute_per_second", 0.0
                        )
                    ),
                    database.get("write_latency_average_ms"),
                    database.get("query_latency_average_ms"),
                    int(operations.get("websocket_clients", 0)),
                    process.get("memory_usage_mb"),
                    process.get("cpu_percent"),
                    int(operations.get("open_data_alerts", 0))
                    + int(operations.get("open_platform_alerts", 0)),
                    json.dumps(snapshot, separators=(",", ":")),
                ),
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM system_metric_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("System metric snapshot was not created")
        return self._decode_system_snapshot(row)

    def list_system_metric_snapshots(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM system_metric_snapshots
                ORDER BY timestamp_utc DESC, snapshot_id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_system_snapshot(row) for row in rows]

    def purge_system_metric_snapshots(self, before_utc: datetime) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM system_metric_snapshots WHERE timestamp_utc < ?",
                (before_utc.astimezone(timezone.utc).isoformat(),),
            )
            return int(cursor.rowcount)

    def get_platform_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM platform_alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        return self._decode_platform_alert(row) if row else None

    def list_platform_alerts(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        component: str | None = None,
        alert_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("status", status),
            ("severity", severity),
            ("component", component),
            ("alert_type", alert_type),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM platform_alerts {where_sql}
                ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                         last_detected_at_utc DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._decode_platform_alert(row) for row in rows]

    def upsert_platform_alert(
        self,
        *,
        active_key: str,
        alert_type: str,
        severity: str,
        component: str,
        title: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT alert_id FROM platform_alerts WHERE active_key = ?",
                (active_key,),
            ).fetchone()
            if existing:
                alert_id = str(existing["alert_id"])
                connection.execute(
                    """
                    UPDATE platform_alerts
                    SET alert_type = ?, severity = ?, status = CASE WHEN status = 'ACKNOWLEDGED' THEN 'ACKNOWLEDGED' ELSE 'OPEN' END, component = ?,
                        title = ?, description = ?, last_detected_at_utc = ?,
                        occurrence_count = occurrence_count + 1,
                        resolved_at_utc = NULL, resolved_by = NULL,
                        resolution_source = NULL, resolution_reason = NULL,
                        metadata_json = ?
                    WHERE alert_id = ?
                    """,
                    (
                        alert_type,
                        severity,
                        component,
                        title,
                        description,
                        now,
                        json.dumps(metadata or {}, separators=(",", ":")),
                        alert_id,
                    ),
                )
            else:
                alert_id = self._generated_id("PLATFORM-ALERT")
                connection.execute(
                    """
                    INSERT INTO platform_alerts (
                        alert_id, active_key, alert_type, severity, status, component,
                        title, description, first_detected_at_utc, last_detected_at_utc,
                        occurrence_count, metadata_json
                    ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        alert_id,
                        active_key,
                        alert_type,
                        severity,
                        component,
                        title,
                        description,
                        now,
                        now,
                        json.dumps(metadata or {}, separators=(",", ":")),
                    ),
                )
        created = self.get_platform_alert(alert_id)
        if created is None:
            raise RuntimeError("Platform alert was not created")
        return created

    def acknowledge_platform_alert(
        self, alert_id: str, actor: str, note: str = ""
    ) -> dict[str, Any] | None:
        current = self.get_platform_alert(alert_id)
        if current is None:
            return None
        if current["status"] == "RESOLVED":
            raise ValueError("Resolved platform alerts cannot be acknowledged")
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE platform_alerts SET status = 'ACKNOWLEDGED',
                    acknowledged_at_utc = ?, acknowledged_by = ?, operator_note = ?
                WHERE alert_id = ?
                """,
                (now, actor, note, alert_id),
            )
        return self.get_platform_alert(alert_id)

    def resolve_platform_alert(
        self,
        alert_id: str,
        actor: str,
        note: str = "",
        *,
        source: str = "MANUAL",
    ) -> dict[str, Any] | None:
        current = self.get_platform_alert(alert_id)
        if current is None:
            return None
        if current["status"] == "RESOLVED":
            return current
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE platform_alerts SET status = 'RESOLVED', active_key = NULL,
                    resolved_at_utc = ?, resolved_by = ?, resolution_source = ?,
                    resolution_reason = ?, operator_note = ? WHERE alert_id = ?
                """,
                (
                    now,
                    actor,
                    source,
                    note
                    or (
                        "Automatically resolved after component recovery."
                        if source == "AUTOMATIC"
                        else "Manually resolved by an operator."
                    ),
                    note,
                    alert_id,
                ),
            )
        return self.get_platform_alert(alert_id)

    def auto_resolve_platform_alert(
        self, active_key: str, reason: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT alert_id FROM platform_alerts WHERE active_key = ?",
                (active_key,),
            ).fetchone()
        if row is None:
            return None
        return self.resolve_platform_alert(
            str(row["alert_id"]), "system", reason, source="AUTOMATIC"
        )

    def database_health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                table_rows = {
                    table: int(
                        connection.execute(
                            f"SELECT COUNT(*) AS total FROM {table}"
                        ).fetchone()["total"]
                    )
                    for table in (
                        "vehicles",
                        "sensors",
                        "missions",
                        "telemetry",
                        "raw_sensor_messages",
                        "vehicle_heartbeats",
                        "mission_events",
                        "integrity_events",
                        "alerts",
                        "application_logs",
                        "system_metric_snapshots",
                        "platform_alerts",
                    )
                }
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
            return {
                "status": (
                    "HEALTHY"
                    if integrity and str(integrity[0]).lower() == "ok"
                    else "UNHEALTHY"
                ),
                "message": "SQLite database is available",
                "response_time_ms": elapsed_ms,
                "database_path": str(self._database_path),
                "database_size_bytes": (
                    self._database_path.stat().st_size
                    if self._database_path.exists()
                    else 0
                ),
                "journal_mode": "WAL",
                "table_rows": table_rows,
            }
        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "message": str(exc),
                "response_time_ms": round((time.perf_counter() - started) * 1000.0, 3),
                "database_path": str(self._database_path),
                "database_size_bytes": (
                    self._database_path.stat().st_size
                    if self._database_path.exists()
                    else 0
                ),
                "table_rows": {},
            }

    # ------------------------------------------------------------------
    # Mission events
    # ------------------------------------------------------------------
    def create_event(
        self, mission_id: str, request: MissionEventCreate
    ) -> dict[str, Any]:
        mission = self.get_mission(mission_id)
        if mission is None:
            raise LookupError("Mission not found")
        if mission["vehicle_id"] != request.vehicle_id:
            raise ValueError("Event vehicle_id does not match the mission vehicle")
        event_id = request.event_id or self._generated_id("EVENT")
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mission_events (
                    event_id, mission_id, vehicle_id, event_type,
                    start_timestamp_utc, end_timestamp_utc, severity, source,
                    description, metadata_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    mission_id,
                    request.vehicle_id,
                    request.event_type,
                    request.start_timestamp_utc.isoformat(),
                    (
                        request.end_timestamp_utc.isoformat()
                        if request.end_timestamp_utc
                        else None
                    ),
                    request.severity,
                    request.source,
                    request.description,
                    json.dumps(request.metadata, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        event = self.get_event(event_id)
        if event is None:
            raise RuntimeError("Event was not created")
        return event

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mission_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return self._decode_event(row) if row else None

    def list_events(self, mission_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM mission_events WHERE mission_id = ?
                ORDER BY start_timestamp_utc ASC, event_id ASC
                """,
                (mission_id,),
            ).fetchall()
        return [self._decode_event(row) for row in rows]

    def update_event(
        self, event_id: str, request: MissionEventUpdate
    ) -> dict[str, Any] | None:
        current = self.get_event(event_id)
        if current is None:
            return None
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return current
        start = updates.get("start_timestamp_utc") or datetime.fromisoformat(
            current["start_timestamp_utc"]
        )
        end = updates.get("end_timestamp_utc")
        if "end_timestamp_utc" not in updates and current["end_timestamp_utc"]:
            end = datetime.fromisoformat(current["end_timestamp_utc"])
        if end and end < start:
            raise ValueError(
                "end_timestamp_utc cannot be earlier than start_timestamp_utc"
            )
        mapping = {
            "event_type": "event_type",
            "start_timestamp_utc": "start_timestamp_utc",
            "end_timestamp_utc": "end_timestamp_utc",
            "severity": "severity",
            "source": "source",
            "description": "description",
            "metadata": "metadata_json",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{mapping[key]} = ?")
            if isinstance(value, datetime):
                value = value.isoformat()
            elif key == "metadata":
                value = json.dumps(value, separators=(",", ":"))
            params.append(value)
        assignments.append("updated_at_utc = ?")
        params.append(self._utc_now().isoformat())
        params.append(event_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE mission_events SET {', '.join(assignments)} WHERE event_id = ?",
                params,
            )
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM mission_events WHERE event_id = ?", (event_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def flatten_for_csv(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for item in records:
            flattened.append(
                {
                    "schema_version": item.get("schema_version"),
                    "message_id": item.get("message_id"),
                    "vehicle_id": item.get("vehicle_id"),
                    "mission_id": item.get("mission_id"),
                    "sequence_no": item.get("sequence_no"),
                    "timestamp_utc": item.get("timestamp_utc"),
                    "received_at_utc": item.get("received_at_utc"),
                    "latency_ms": item.get("latency_ms"),
                    "source": item.get("source"),
                    "coordinate_frame": item.get("coordinate_frame"),
                    "x_m": item["position"]["x_m"],
                    "y_m": item["position"]["y_m"],
                    "z_m": item["position"]["z_m"],
                    "latitude_deg": item["position"].get("latitude_deg"),
                    "longitude_deg": item["position"].get("longitude_deg"),
                    "vx_mps": item["velocity"]["vx_mps"],
                    "vy_mps": item["velocity"]["vy_mps"],
                    "vz_mps": item["velocity"]["vz_mps"],
                    "speed_mps": item["velocity"]["speed_mps"],
                    "ax_mps2": item["acceleration"]["ax_mps2"],
                    "ay_mps2": item["acceleration"]["ay_mps2"],
                    "az_mps2": item["acceleration"]["az_mps2"],
                    "heading_deg": item["orientation"]["heading_deg"],
                    "pitch_deg": item["orientation"]["pitch_deg"],
                    "roll_deg": item["orientation"]["roll_deg"],
                    "battery_percent": item["state"]["battery_percent"],
                    "operating_mode": item["state"]["operating_mode"],
                    "autonomy_enabled": item["state"]["autonomy_enabled"],
                    "emergency_stop": item["state"]["emergency_stop"],
                    "quality_valid": item["quality"]["valid"],
                    "position_source": item["quality"]["position_source"],
                    "confidence": item["quality"]["confidence"],
                }
            )
        return flattened
