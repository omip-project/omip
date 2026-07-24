from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import sqlite3
import time
import zipfile
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import (FastAPI, HTTPException, Query, Response, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .api import create_acquisition_router, create_health_router
from .config import (BACKUP_DIR, DATABASE_PATH, DEGRADED_THRESHOLD_S,
                     EXPORT_DIR, MQTT_ENABLED, MQTT_HEARTBEAT_TOPIC, MQTT_HOST,
                     MQTT_PORT, MQTT_TELEMETRY_TOPIC, MQTT_TOPIC,
                     ONLINE_THRESHOLD_S, PROJECT_DIR, PUBLIC_API_BASE,
                     SCENARIOS_DIR, STATIC_DIR,
                     SYSTEM_INGESTION_REJECTION_WARNING_RATIO,
                     SYSTEM_MEMORY_WARNING_MB, SYSTEM_SNAPSHOT_INTERVAL_S,
                     SYSTEM_SNAPSHOT_RETENTION_DAYS)
from .database import OmipRepository
from .environment_context import EnvironmentContextService
from .integrity_service import DataIntegrityService
from .mqtt_bridge import MqttRuntimeManager
from .normalizer import RawMessageNormalizer
from .obstacle_interaction import ObstacleInteractionService
from .safety_analytics import SafetyAnalyticsService
from .schemas import (AlertActionRequest, AlertStatus, AlertType,
                      BackupCreateRequest, CleanupExecuteRequest,
                      EnvironmentConstraintCreate, EnvironmentConstraintUpdate,
                      EventSeverity, ExportJobCreate, ExternalFieldCreate,
                      ExternalFieldUpdate, IntegrityCheckType, MissionCreate,
                      MissionEnvironmentCapture, MissionEventCreate,
                      MissionEventUpdate, MissionStatus, ObstacleCreate, ObstacleUpdate, RawMessageType,
                      RawSensorMessage, RetentionPolicyUpdate, ScenarioCreate,
                      ScenarioUpdate, SensorCreate, SensorUpdate,
                      SimulationRunCreate, SimulationRunStopRequest,
                      TelemetryFrame, VehicleCreate, VehicleHeartbeat,
                      VehicleProfileCreate, VehicleProfileUpdate,
                      VehicleUpdate)
from .simulation_runs import SimulationRunManager
from .storage_management import StorageManager, build_export_content
from .system_monitoring import RuntimeMetricsService, SystemHealthService
from .vehicle_profiles import (BUILT_IN_PROFILES,
                               VEHICLE_PARAMETER_DEFINITIONS, deep_merge,
                               validate_parameters, vehicle_type_catalogue)

logger = logging.getLogger(__name__)

repository = OmipRepository(
    DATABASE_PATH,
    online_threshold_s=ONLINE_THRESHOLD_S,
    degraded_threshold_s=DEGRADED_THRESHOLD_S,
)
normalizer = RawMessageNormalizer()
runtime_metrics = RuntimeMetricsService()
_storage_manager_cache: tuple[str, StorageManager] | None = None
_simulation_manager_cache: tuple[str, SimulationRunManager] | None = None
_environment_context_cache: tuple[str, EnvironmentContextService] | None = None
_obstacle_interaction_cache: tuple[str, ObstacleInteractionService] | None = None
_safety_analytics_cache: tuple[str, SafetyAnalyticsService] | None = None


def _storage_manager() -> StorageManager:
    global _storage_manager_cache
    database_key = str(repository._database_path)
    if _storage_manager_cache is None or _storage_manager_cache[0] != database_key:
        _storage_manager_cache = (
            database_key,
            StorageManager(repository, EXPORT_DIR, BACKUP_DIR),
        )
    return _storage_manager_cache[1]


def _simulation_manager() -> SimulationRunManager:
    global _simulation_manager_cache
    repository_key = str(repository._database_path)
    if (
        _simulation_manager_cache is None
        or _simulation_manager_cache[0] != repository_key
    ):
        _simulation_manager_cache = (
            repository_key,
            SimulationRunManager(repository, PROJECT_DIR, api_base=PUBLIC_API_BASE),
        )
    return _simulation_manager_cache[1]


def _environment_context() -> EnvironmentContextService:
    global _environment_context_cache
    repository_key = str(repository._database_path)
    if (
        _environment_context_cache is None
        or _environment_context_cache[0] != repository_key
    ):
        _environment_context_cache = (
            repository_key,
            EnvironmentContextService(repository, SCENARIOS_DIR),
        )
    return _environment_context_cache[1]


def _obstacle_interaction_service() -> ObstacleInteractionService:
    global _obstacle_interaction_cache
    repository_key = str(repository._database_path)
    if (
        _obstacle_interaction_cache is None
        or _obstacle_interaction_cache[0] != repository_key
    ):
        _obstacle_interaction_cache = (
            repository_key,
            ObstacleInteractionService(repository, _environment_context()),
        )
    return _obstacle_interaction_cache[1]


def _safety_analytics_service() -> SafetyAnalyticsService:
    global _safety_analytics_cache
    repository_key = str(repository._database_path)
    if _safety_analytics_cache is None or _safety_analytics_cache[0] != repository_key:
        _safety_analytics_cache = (
            repository_key,
            SafetyAnalyticsService(
                repository, _environment_context(), _obstacle_interaction_service()
            ),
        )
    return _safety_analytics_cache[1]


def _seed_vehicle_profiles() -> None:
    repository.seed_vehicle_parameter_definitions(VEHICLE_PARAMETER_DEFINITIONS)
    for item in BUILT_IN_PROFILES:
        repository.upsert_vehicle_profile(
            VehicleProfileCreate.model_validate(item), built_in=True
        )


def _run_export_job(job_id: str, mission_id: str, export_format: str) -> None:
    manager = _storage_manager()
    try:
        manager.mark_export_running(job_id)
        content, file_name, media_type = build_export_content(
            repository, mission_id, export_format
        )
        output = manager.export_dir / f"{job_id}-{file_name}"
        output.write_bytes(content)
        manager.complete_export_job(job_id, output, {"media_type": media_type})
    except Exception as exc:
        manager.fail_export_job(job_id, str(exc))


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)
        failed: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception:
                failed.append(connection)
        if failed:
            async with self._lock:
                for connection in failed:
                    self._connections.discard(connection)

    @property
    def count(self) -> int:
        return len(self._connections)


telemetry_connections = ConnectionManager()
stream_connections = ConnectionManager()
mqtt_runtime = MqttRuntimeManager(
    host=MQTT_HOST,
    port=MQTT_PORT,
    raw_topic=MQTT_TOPIC,
    telemetry_topic=MQTT_TELEMETRY_TOPIC,
    heartbeat_topic=MQTT_HEARTBEAT_TOPIC,
)


def _system_health_service() -> SystemHealthService:
    # The repository is replaced by tests, so create the service lazily.
    return SystemHealthService(
        repository,
        runtime_metrics,
        mqtt_runtime,
        telemetry_connections,
        stream_connections,
        memory_warning_mb=SYSTEM_MEMORY_WARNING_MB,
        rejection_warning_ratio=SYSTEM_INGESTION_REJECTION_WARNING_RATIO,
    )


async def _application_log(
    level: str,
    component: str,
    event_type: str,
    message: str,
    *,
    vehicle_id: str | None = None,
    sensor_id: str | None = None,
    mission_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        record = repository.create_application_log(
            level=level,
            component=component,
            event_type=event_type,
            message=message,
            vehicle_id=vehicle_id,
            sensor_id=sensor_id,
            mission_id=mission_id,
            details=details or {},
        )
        await stream_connections.broadcast(
            {"stream_type": "application_log", "data": record}
        )
        return record
    except Exception as exc:  # Logging must never break ingestion.
        logger.warning("Could not persist application log: %s", exc)
        return None


PLATFORM_CONDITIONS = {
    "database-unavailable": ("DATABASE_UNAVAILABLE", "database"),
    "mqtt-disconnected": ("MQTT_DISCONNECTED", "mqtt"),
    "high-ingestion-failure-rate": ("HIGH_INGESTION_FAILURE_RATE", "ingestion"),
    "high-memory-usage": ("HIGH_MEMORY_USAGE", "process"),
    "integrity-engine-failure": ("INTEGRITY_ENGINE_FAILURE", "integrity_engine"),
}


async def _evaluate_platform_health(
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    health = health or _system_health_service().health()
    components = health.get("components", {})
    active: dict[str, dict[str, str]] = {}
    for key, (alert_type, component_name) in PLATFORM_CONDITIONS.items():
        component = components.get(component_name, {})
        status = component.get("status", "UNKNOWN")
        should_alert = status in {"DEGRADED", "UNHEALTHY"}
        # Disabled MQTT is an intentional UNKNOWN state, not a fault.
        if key == "mqtt-disconnected":
            should_alert = bool(component.get("enabled")) and not bool(
                component.get("connected")
            )
        if should_alert:
            severity = "CRITICAL" if status == "UNHEALTHY" else "WARNING"
            active[key] = {
                "alert_type": alert_type,
                "severity": severity,
                "component": component_name,
                "title": alert_type.replace("_", " ").title(),
                "description": str(
                    component.get("message", f"{component_name} is {status}")
                ),
            }

    for key, data in active.items():
        alert = repository.upsert_platform_alert(
            active_key=key, metadata=components.get(data["component"], {}), **data
        )
        await stream_connections.broadcast(
            {"stream_type": "platform_alert", "data": alert}
        )

    for key in PLATFORM_CONDITIONS:
        if key not in active:
            resolved = repository.auto_resolve_platform_alert(
                key, "Component returned to a healthy operating state."
            )
            if resolved:
                await stream_connections.broadcast(
                    {"stream_type": "platform_alert", "data": resolved}
                )
    return health


async def _system_monitor_loop() -> None:
    while True:
        try:
            health = await _evaluate_platform_health()
            snapshot = repository.create_system_metric_snapshot(health)
            await stream_connections.broadcast(
                {"stream_type": "system_metric", "data": snapshot}
            )
            repository.purge_system_metric_snapshots(
                datetime.now(timezone.utc)
                - timedelta(days=SYSTEM_SNAPSHOT_RETENTION_DAYS)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("System monitoring cycle failed")
            runtime_metrics.increment("system_monitor_failures")
            await _application_log(
                "ERROR",
                "SYSTEM",
                "MONITORING_CYCLE_FAILURE",
                "System monitoring cycle failed.",
                details={"error": str(exc)},
            )
        await asyncio.sleep(SYSTEM_SNAPSHOT_INTERVAL_S)


def _integrity_service() -> DataIntegrityService:
    # The repository is replaced by several tests, so create the service lazily.
    return DataIntegrityService(repository)


async def _record_integrity(findings: list[Any]) -> dict[str, list[dict[str, Any]]]:
    recorded = repository.record_integrity_findings(findings)
    for event in recorded["integrity_events"]:
        await stream_connections.broadcast(
            {"stream_type": "integrity_event", "data": event}
        )
    for alert in recorded["alerts"]:
        await stream_connections.broadcast({"stream_type": "alert", "data": alert})
    return recorded


async def _broadcast_resolved_alerts(alerts: list[dict[str, Any]]) -> None:
    for alert in alerts:
        await stream_connections.broadcast({"stream_type": "alert", "data": alert})


async def _store_telemetry(frame: TelemetryFrame) -> dict[str, Any]:
    runtime_metrics.increment("telemetry_frames_received", rate_event=True)
    repository.ensure_mission(frame.mission_id, frame.vehicle_id, frame.timestamp_utc)
    try:
        analysis = _integrity_service().analyse_telemetry_detailed(frame)
    except Exception:
        runtime_metrics.increment("integrity_engine_failures")
        raise
    findings = analysis.findings
    duplicate_message_id = any(
        finding.details.get("duplicate_kind") == "MESSAGE_ID" for finding in findings
    )
    if duplicate_message_id:
        await _record_integrity(findings)
        started = time.perf_counter()
        try:
            return repository.insert_telemetry(frame)
        finally:
            runtime_metrics.record_database_write(
                (time.perf_counter() - started) * 1000.0, success=False
            )

    started = time.perf_counter()
    try:
        stored = repository.insert_telemetry(frame)
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=True
        )
    except Exception:
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=False
        )
        raise
    await _record_integrity(findings)
    resolved = repository.auto_resolve_recovered_alerts(
        mission_id=frame.mission_id,
        sensor_id=None,
        evaluated_types=analysis.evaluated_recoverable_types,
        active_types=analysis.active_recoverable_types,
    )
    await _broadcast_resolved_alerts(resolved)
    interaction = None
    try:
        interaction = _obstacle_interaction_service().analyse(stored)
    except Exception as exc:
        logger.warning(
            "Obstacle interaction analysis failed for %s: %s", frame.message_id, exc
        )
        await _application_log(
            "WARNING",
            "OBSTACLE_INTERACTION",
            "ANALYSIS_FAILURE",
            "Obstacle interaction analysis failed.",
            vehicle_id=frame.vehicle_id,
            mission_id=frame.mission_id,
            details={"message_id": str(frame.message_id), "error": str(exc)},
        )
    if interaction is not None:
        await stream_connections.broadcast(
            {"stream_type": "obstacle_interaction", "data": interaction}
        )
    try:
        safety_result = _safety_analytics_service().analyse(stored, interaction)
        for violation in safety_result.get("violations", []):
            await stream_connections.broadcast(
                {"stream_type": "constraint_violation", "data": violation}
            )
        for violation in safety_result.get("resolved", []):
            await stream_connections.broadcast(
                {"stream_type": "constraint_violation", "data": violation}
            )
        if safety_result.get("near_miss"):
            await stream_connections.broadcast(
                {"stream_type": "near_miss", "data": safety_result["near_miss"]}
            )
    except Exception as exc:
        logger.warning("Safety analytics failed for %s: %s", frame.message_id, exc)
    await telemetry_connections.broadcast(stored)
    await stream_connections.broadcast({"stream_type": "telemetry", "data": stored})
    return stored


async def _store_raw(
    message: RawSensorMessage,
    transport: Literal["HTTP", "MQTT", "FILE_UPLOAD", "SIMULATOR"] = "HTTP",
    topic: str | None = None,
) -> dict[str, Any]:
    runtime_metrics.increment("raw_messages_received", rate_event=True)
    repository.ensure_sensor(message)
    repository.ensure_mission(
        message.mission_id, message.vehicle_id, message.timestamp_utc
    )
    try:
        analysis = _integrity_service().analyse_raw_detailed(message)
    except Exception:
        runtime_metrics.increment("integrity_engine_failures")
        raise
    findings = analysis.findings
    duplicate_message_id = any(
        finding.details.get("duplicate_kind") == "MESSAGE_ID" for finding in findings
    )
    if duplicate_message_id:
        await _record_integrity(findings)
        started = time.perf_counter()
        try:
            duplicate = repository.insert_raw_message(
                message, transport=transport, topic=topic
            )
            runtime_metrics.record_database_write(
                (time.perf_counter() - started) * 1000.0, success=True
            )
            return {"raw_message": duplicate, "normalised_telemetry": None}
        except Exception:
            runtime_metrics.record_database_write(
                (time.perf_counter() - started) * 1000.0, success=False
            )
            raise

    started = time.perf_counter()
    try:
        stored_raw = repository.insert_raw_message(
            message, transport=transport, topic=topic
        )
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=True
        )
    except Exception:
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=False
        )
        raise
    await _record_integrity(findings)
    resolved = repository.auto_resolve_recovered_alerts(
        mission_id=message.mission_id,
        sensor_id=message.sensor_id,
        evaluated_types=analysis.evaluated_recoverable_types,
        active_types=analysis.active_recoverable_types,
    )
    await _broadcast_resolved_alerts(resolved)
    await stream_connections.broadcast(
        {"stream_type": "raw_sensor", "data": stored_raw}
    )
    normalised = normalizer.process(message)
    stored_telemetry: dict[str, Any] | None = None
    if normalised is not None:
        stored_telemetry = await _store_telemetry(normalised)
    return {"raw_message": stored_raw, "normalised_telemetry": stored_telemetry}


async def _store_heartbeat(
    heartbeat: VehicleHeartbeat,
    transport: Literal["HTTP", "MQTT", "FILE_UPLOAD", "SIMULATOR"] = "HTTP",
) -> dict[str, Any]:
    runtime_metrics.increment("heartbeats_received", rate_event=True)
    started = time.perf_counter()
    try:
        stored = repository.insert_heartbeat(heartbeat, transport=transport)
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=True
        )
    except Exception:
        runtime_metrics.record_database_write(
            (time.perf_counter() - started) * 1000.0, success=False
        )
        raise
    await stream_connections.broadcast({"stream_type": "heartbeat", "data": stored})
    return stored


async def _handle_mqtt(topic: str, payload: dict[str, Any]) -> None:
    runtime_metrics.increment("mqtt_messages_received", rate_event=True)
    try:
        if topic.endswith("/heartbeat"):
            await _store_heartbeat(
                VehicleHeartbeat.model_validate(payload), transport="MQTT"
            )
        elif topic.endswith("/telemetry"):
            await _store_telemetry(TelemetryFrame.model_validate(payload))
        else:
            await _store_raw(
                RawSensorMessage.model_validate(payload), transport="MQTT", topic=topic
            )
        runtime_metrics.increment("messages_accepted", rate_event=True)
    except (ValidationError, sqlite3.IntegrityError, LookupError, ValueError) as exc:
        runtime_metrics.increment("messages_rejected", rate_event=True)
        runtime_metrics.increment("mqtt_ingestion_failures")
        logger.warning("Rejected MQTT message on %s: %s", topic, exc)
        await _application_log(
            "WARNING",
            "MQTT",
            "MESSAGE_REJECTED",
            "An MQTT message was rejected.",
            details={"topic": topic, "error": str(exc)},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor_task: asyncio.Task[Any] | None = None
    _seed_vehicle_profiles()
    _environment_context()
    _obstacle_interaction_service()
    _safety_analytics_service()
    await _application_log(
        "INFO", "SYSTEM", "SERVICE_START", "OMIP v0.5.2 service started."
    )
    if MQTT_ENABLED:
        status = await mqtt_runtime.enable(
            loop=asyncio.get_running_loop(),
            handler=_handle_mqtt,
        )
        if status.get("last_error"):
            logger.warning("MQTT bridge did not start: %s", status["last_error"])
    monitor_task = asyncio.create_task(
        _system_monitor_loop(), name="omip-system-monitor"
    )
    try:
        yield
    finally:
        if monitor_task:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task
        await mqtt_runtime.disable()
        _simulation_manager().stop_all()
        await _application_log(
            "INFO", "SYSTEM", "SERVICE_STOP", "OMIP v0.5.2 service stopped."
        )


app = FastAPI(
    title="OMIP Platform API",
    version="0.5.2",
    description=(
        "Multi-vehicle acquisition platform with data-integrity detection, runtime system metrics, "
        "component health monitoring, structured application logs, platform alerts, MQTT control, "
        "mission replay, vehicle profiles, type-aware simulation-run management, environment context, obstacles, vehicle-specific constraints and complete data export."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ingestion_metrics_middleware(request, call_next):
    monitored = request.method in {"POST", "PUT"} and (
        request.url.path == "/api/v1/telemetry"
        or request.url.path.startswith("/api/v1/raw-messages")
        or request.url.path.endswith("/heartbeat")
    )
    if monitored:
        runtime_metrics.increment("http_messages_received", rate_event=True)
    try:
        response = await call_next(request)
    except Exception:
        if monitored:
            runtime_metrics.increment("messages_rejected", rate_event=True)
            runtime_metrics.increment("http_ingestion_failures")
        raise
    if monitored:
        if response.status_code < 400:
            runtime_metrics.increment("messages_accepted", rate_event=True)
        else:
            runtime_metrics.increment("messages_rejected", rate_event=True)
            runtime_metrics.increment("http_ingestion_failures")
    return response


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"}
    )


app.include_router(
    create_health_router(mqtt_status=lambda: mqtt_runtime.status())
)
app.include_router(
    create_acquisition_router(
        get_mqtt_runtime=lambda: mqtt_runtime,
        telemetry_connections=telemetry_connections,
        stream_connections=stream_connections,
        database_path=DATABASE_PATH,
        mqtt_handler=_handle_mqtt,
        broadcast=stream_connections.broadcast,
    )
)


# ---------------------------------------------------------------------------
# System monitoring and operational health
# ---------------------------------------------------------------------------
@app.get("/api/v1/system/health")
async def system_health() -> dict[str, Any]:
    return await _evaluate_platform_health()


@app.get("/api/v1/system/metrics")
def system_metrics() -> dict[str, Any]:
    health = _system_health_service().health()
    return {
        "captured_at_utc": health["captured_at_utc"],
        "overall_status": health["overall_status"],
        "uptime_seconds": health["uptime_seconds"],
        "runtime": health["runtime"],
        "operations": health["operations"],
    }


@app.get("/api/v1/system/database")
def system_database() -> dict[str, Any]:
    started = time.perf_counter()
    result = repository.database_health()
    runtime_metrics.record_database_query(
        (time.perf_counter() - started) * 1000.0,
        success=result.get("status") == "HEALTHY",
    )
    return result


@app.get("/api/v1/system/logs")
def system_logs(
    level: str | None = None,
    component: str | None = None,
    event_type: str | None = None,
    vehicle_id: str | None = None,
    sensor_id: str | None = None,
    mission_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[dict[str, Any]]:
    return repository.list_application_logs(
        level=level,
        component=component,
        event_type=event_type,
        vehicle_id=vehicle_id,
        sensor_id=sensor_id,
        mission_id=mission_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


@app.get("/api/v1/system/logs/{log_id}")
def system_log(log_id: str) -> dict[str, Any]:
    record = repository.get_application_log(log_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application log not found")
    return record


@app.get("/api/v1/system/metrics/snapshots")
def system_metric_snapshots(
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[dict[str, Any]]:
    return repository.list_system_metric_snapshots(limit)


@app.get("/api/v1/system/platform-alerts")
def platform_alerts(
    status: str | None = None,
    severity: str | None = None,
    component: str | None = None,
    alert_type: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[dict[str, Any]]:
    return repository.list_platform_alerts(
        status=status,
        severity=severity,
        component=component,
        alert_type=alert_type,
        limit=limit,
    )


@app.get("/api/v1/system/platform-alerts/{alert_id}")
def platform_alert(alert_id: str) -> dict[str, Any]:
    record = repository.get_platform_alert(alert_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Platform alert not found")
    return record


@app.post("/api/v1/system/platform-alerts/{alert_id}/acknowledge")
async def acknowledge_platform_alert(
    alert_id: str, request: AlertActionRequest
) -> dict[str, Any]:
    try:
        alert = repository.acknowledge_platform_alert(
            alert_id, request.actor, request.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if alert is None:
        raise HTTPException(status_code=404, detail="Platform alert not found")
    await stream_connections.broadcast({"stream_type": "platform_alert", "data": alert})
    await _application_log(
        "INFO",
        "SYSTEM",
        "PLATFORM_ALERT_ACKNOWLEDGED",
        f"Platform alert {alert_id} was acknowledged.",
        details={"actor": request.actor},
    )
    return alert


@app.post("/api/v1/system/platform-alerts/{alert_id}/resolve")
async def resolve_platform_alert(
    alert_id: str, request: AlertActionRequest
) -> dict[str, Any]:
    alert = repository.resolve_platform_alert(alert_id, request.actor, request.note)
    if alert is None:
        raise HTTPException(status_code=404, detail="Platform alert not found")
    await stream_connections.broadcast({"stream_type": "platform_alert", "data": alert})
    await _application_log(
        "INFO",
        "SYSTEM",
        "PLATFORM_ALERT_RESOLVED",
        f"Platform alert {alert_id} was resolved.",
        details={"actor": request.actor},
    )
    return alert


# ---------------------------------------------------------------------------
# Vehicle registry
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# v0.4.3 storage lifecycle, pagination, export jobs and maintenance
# ---------------------------------------------------------------------------
@app.get("/api/v1/storage/summary")
def storage_summary() -> dict[str, Any]:
    return _storage_manager().storage_summary()


@app.get("/api/v1/storage/tables")
def storage_tables() -> list[dict[str, Any]]:
    return _storage_manager().table_statistics()


@app.get("/api/v1/storage/retention-policy")
def get_retention_policy() -> dict[str, int]:
    return _storage_manager().get_retention_policy()


@app.put("/api/v1/storage/retention-policy")
async def update_retention_policy(request: RetentionPolicyUpdate) -> dict[str, int]:
    try:
        policy = _storage_manager().update_retention_policy(
            request.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _application_log(
        "INFO",
        "STORAGE",
        "RETENTION_POLICY_UPDATED",
        "Storage retention policy updated.",
        details=policy,
    )
    return policy


@app.get("/api/v1/storage/cleanup/preview")
def storage_cleanup_preview() -> dict[str, Any]:
    return _storage_manager().cleanup_preview()


@app.post("/api/v1/storage/cleanup/execute")
async def storage_cleanup_execute(request: CleanupExecuteRequest) -> dict[str, Any]:
    try:
        result = _storage_manager().execute_cleanup(request.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _application_log(
        "WARNING",
        "STORAGE",
        "MANUAL_CLEANUP",
        "Manual retention cleanup executed.",
        details=result,
    )
    return result


@app.get("/api/v1/missions/{mission_id}/telemetry/page")
def mission_telemetry_page(
    mission_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
    sort_order: Literal["asc", "desc"] = "asc",
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _storage_manager().mission_telemetry_page(
        mission_id, page, page_size, sort_order, start_time, end_time
    )


@app.get("/api/v1/missions/{mission_id}/raw-messages/page")
def mission_raw_page(
    mission_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=5000),
    sort_order: Literal["asc", "desc"] = "asc",
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _storage_manager().mission_raw_page(
        mission_id, page, page_size, sort_order, start_time, end_time
    )


@app.get("/api/v1/storage/application-logs/page")
def system_logs_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    level: str | None = None,
) -> dict[str, Any]:
    return _storage_manager().application_logs_page(page, page_size, level)


@app.get("/api/v1/missions/{mission_id}/delete-preview")
def mission_delete_preview(mission_id: str) -> dict[str, Any]:
    result = _storage_manager().mission_delete_preview(mission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return result


@app.delete("/api/v1/missions/{mission_id}")
async def delete_mission_data(
    mission_id: str, confirm: str = Query(min_length=1)
) -> dict[str, Any]:
    try:
        result = _storage_manager().delete_mission(mission_id, confirm)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    await _application_log(
        "WARNING",
        "STORAGE",
        "MISSION_DELETED",
        f"Mission {mission_id} and linked data deleted.",
        mission_id=mission_id,
        details=result,
    )
    return result


@app.post("/api/v1/export-jobs", status_code=202)
async def create_export_job(request: ExportJobCreate) -> dict[str, Any]:
    try:
        job = _storage_manager().create_export_job(
            request.mission_id, request.export_format
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asyncio.create_task(
        asyncio.to_thread(
            _run_export_job, job["job_id"], request.mission_id, request.export_format
        )
    )
    return job


@app.get("/api/v1/export-jobs")
def list_export_jobs(
    mission_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return _storage_manager().list_export_jobs(mission_id, limit)


@app.get("/api/v1/export-jobs/{job_id}")
def get_export_job(job_id: str) -> dict[str, Any]:
    job = _storage_manager().get_export_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job


@app.get("/api/v1/export-jobs/{job_id}/download")
def download_export_job(job_id: str) -> FileResponse:
    job = _storage_manager().get_export_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job["state"] != "COMPLETED" or not job.get("file_path"):
        raise HTTPException(status_code=409, detail="Export job is not ready")
    path = Path(job["file_path"])
    if not path.exists():
        raise HTTPException(
            status_code=410, detail="Export file is no longer available"
        )
    return FileResponse(path, filename=job.get("file_name") or path.name)


@app.post("/api/v1/storage/backups", status_code=201)
async def create_storage_backup(request: BackupCreateRequest) -> dict[str, Any]:
    result = await asyncio.to_thread(_storage_manager().create_backup, request.label)
    await _application_log(
        "INFO",
        "STORAGE",
        "DATABASE_BACKUP",
        f"Database backup {result.get('state', 'UNKNOWN').lower()}.",
        details=result,
    )
    return result


@app.get("/api/v1/storage/backups")
def list_storage_backups(
    limit: int = Query(default=100, ge=1, le=1000)
) -> list[dict[str, Any]]:
    return _storage_manager().list_backups(limit)


@app.get("/api/v1/storage/backups/{backup_id}/download")
def download_storage_backup(backup_id: str) -> FileResponse:
    backup = _storage_manager().get_backup(backup_id)
    if backup is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    if backup["state"] != "COMPLETED" or not backup.get("file_path"):
        raise HTTPException(status_code=409, detail="Backup is not ready")
    path = Path(backup["file_path"])
    if not path.exists():
        raise HTTPException(
            status_code=410, detail="Backup file is no longer available"
        )
    return FileResponse(path, filename=backup.get("file_name") or path.name)


@app.get("/api/v1/storage/integrity-check")
def storage_integrity_check() -> dict[str, Any]:
    return _storage_manager().integrity_check()


@app.post("/api/v1/storage/maintenance/analyze")
async def storage_analyze() -> dict[str, Any]:
    result = await asyncio.to_thread(_storage_manager().analyze)
    await _application_log(
        "INFO",
        "STORAGE",
        "DATABASE_ANALYZE",
        "SQLite ANALYZE completed.",
        details=result,
    )
    return result


@app.post("/api/v1/storage/maintenance/checkpoint")
async def storage_checkpoint() -> dict[str, Any]:
    result = await asyncio.to_thread(_storage_manager().checkpoint)
    await _application_log(
        "INFO",
        "STORAGE",
        "WAL_CHECKPOINT",
        "SQLite WAL checkpoint completed.",
        details=result,
    )
    return result


@app.post("/api/v1/storage/maintenance/vacuum")
async def storage_vacuum() -> dict[str, Any]:
    result = await asyncio.to_thread(_storage_manager().vacuum)
    await _application_log(
        "WARNING",
        "STORAGE",
        "DATABASE_VACUUM",
        "SQLite VACUUM completed.",
        details=result,
    )
    return result


# ---------------------------------------------------------------------------
# Vehicle types, profiles and simulation-run management (v0.5.0)
# ---------------------------------------------------------------------------
@app.get("/api/v1/vehicle-types")
def list_vehicle_types() -> list[dict[str, Any]]:
    return vehicle_type_catalogue()


@app.get("/api/v1/vehicle-parameter-definitions")
def list_vehicle_parameter_definitions(
    vehicle_type: str | None = None,
) -> list[dict[str, Any]]:
    return repository.list_vehicle_parameter_definitions(vehicle_type)


@app.get("/api/v1/vehicle-profiles")
def list_vehicle_profiles(
    vehicle_type: str | None = None,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    return repository.list_vehicle_profiles(vehicle_type, enabled_only)


@app.post("/api/v1/vehicle-profiles", status_code=201)
async def create_vehicle_profile(request: VehicleProfileCreate) -> dict[str, Any]:
    if request.vehicle_type not in VEHICLE_PARAMETER_DEFINITIONS:
        raise HTTPException(
            status_code=422, detail="A concrete UGV, UAV, AUV or USV type is required"
        )
    errors = validate_parameters(request.vehicle_type, request.parameters)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid vehicle parameters", "errors": errors},
        )
    if repository.get_vehicle_profile(request.profile_id):
        raise HTTPException(status_code=409, detail="Vehicle profile ID already exists")
    profile = repository.upsert_vehicle_profile(request, built_in=False)
    await _application_log(
        "INFO",
        "SIMULATION",
        "VEHICLE_PROFILE_CREATED",
        f"Vehicle profile {request.profile_id} created.",
        details={"vehicle_type": request.vehicle_type},
    )
    return profile


@app.get("/api/v1/vehicle-profiles/{profile_id}")
def get_vehicle_profile(profile_id: str) -> dict[str, Any]:
    profile = repository.get_vehicle_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Vehicle profile not found")
    return profile


@app.put("/api/v1/vehicle-profiles/{profile_id}")
async def update_vehicle_profile(
    profile_id: str, request: VehicleProfileUpdate
) -> dict[str, Any]:
    current = repository.get_vehicle_profile(profile_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Vehicle profile not found")
    parameters = (
        request.parameters if request.parameters is not None else current["parameters"]
    )
    errors = validate_parameters(current["vehicle_type"], parameters)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid vehicle parameters", "errors": errors},
        )
    updated = repository.update_vehicle_profile(profile_id, request)
    await _application_log(
        "INFO",
        "SIMULATION",
        "VEHICLE_PROFILE_UPDATED",
        f"Vehicle profile {profile_id} updated.",
    )
    return updated or current


@app.delete("/api/v1/vehicle-profiles/{profile_id}", status_code=204)
def delete_vehicle_profile(profile_id: str) -> Response:
    try:
        deleted = repository.delete_vehicle_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Vehicle profile not found")
    return Response(status_code=204)


@app.get("/api/v1/scenarios")
def list_scenarios(enabled_only: bool = False) -> list[dict[str, Any]]:
    return _environment_context().list_scenarios(enabled_only=enabled_only)


@app.post("/api/v1/scenarios", status_code=201)
async def create_scenario(request: ScenarioCreate) -> dict[str, Any]:
    if _environment_context().get_scenario(request.scenario_id, include_items=False):
        raise HTTPException(status_code=409, detail="Scenario ID already exists")
    scenario = _environment_context().upsert_scenario(request, built_in=False)
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "SCENARIO_CREATED",
        f"Scenario {request.scenario_id} created.",
        details={"version": scenario["version"]},
    )
    return scenario


@app.get("/api/v1/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict[str, Any]:
    scenario = _environment_context().get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@app.put("/api/v1/scenarios/{scenario_id}")
async def update_scenario(scenario_id: str, request: ScenarioUpdate) -> dict[str, Any]:
    scenario = _environment_context().update_scenario(scenario_id, request)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "SCENARIO_UPDATED",
        f"Scenario {scenario_id} updated.",
        details={"version": scenario["version"]},
    )
    return scenario


@app.delete("/api/v1/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str) -> Response:
    try:
        deleted = _environment_context().delete_scenario(scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return Response(status_code=204)


@app.post("/api/v1/scenarios/{scenario_id}/obstacles", status_code=201)
async def create_obstacle(scenario_id: str, request: ObstacleCreate) -> dict[str, Any]:
    try:
        item = _environment_context().create_obstacle(scenario_id, request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "OBSTACLE_CREATED",
        f"Obstacle {item['obstacle_id']} created.",
        details={"scenario_id": scenario_id},
    )
    return item


@app.put("/api/v1/obstacles/{obstacle_id}")
def update_obstacle(obstacle_id: str, request: ObstacleUpdate) -> dict[str, Any]:
    item = _environment_context().update_obstacle(obstacle_id, request)
    if item is None:
        raise HTTPException(status_code=404, detail="Obstacle not found")
    return item


@app.delete("/api/v1/obstacles/{obstacle_id}", status_code=204)
def delete_obstacle(obstacle_id: str) -> Response:
    if not _environment_context().delete_obstacle(obstacle_id):
        raise HTTPException(status_code=404, detail="Obstacle not found")
    return Response(status_code=204)


@app.post("/api/v1/scenarios/{scenario_id}/constraints", status_code=201)
async def create_environment_constraint(
    scenario_id: str, request: EnvironmentConstraintCreate
) -> dict[str, Any]:
    try:
        item = _environment_context().create_constraint(scenario_id, request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "CONSTRAINT_CREATED",
        f"Constraint {item['constraint_id']} created.",
        details={"scenario_id": scenario_id},
    )
    return item


@app.put("/api/v1/constraints/{constraint_id}")
def update_environment_constraint(
    constraint_id: str, request: EnvironmentConstraintUpdate
) -> dict[str, Any]:
    item = _environment_context().update_constraint(constraint_id, request)
    if item is None:
        raise HTTPException(status_code=404, detail="Constraint not found")
    return item


@app.delete("/api/v1/constraints/{constraint_id}", status_code=204)
def delete_environment_constraint(constraint_id: str) -> Response:
    if not _environment_context().delete_constraint(constraint_id):
        raise HTTPException(status_code=404, detail="Constraint not found")
    return Response(status_code=204)


@app.post("/api/v1/scenarios/{scenario_id}/external-fields", status_code=201)
async def create_external_field(
    scenario_id: str, request: ExternalFieldCreate
) -> dict[str, Any]:
    try:
        item = _environment_context().create_external_field(scenario_id, request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "EXTERNAL_FIELD_CREATED",
        f"External field {item['field_id']} created.",
        details={"scenario_id": scenario_id},
    )
    return item


@app.put("/api/v1/external-fields/{field_id}")
def update_external_field(
    field_id: str, request: ExternalFieldUpdate
) -> dict[str, Any]:
    item = _environment_context().update_external_field(field_id, request)
    if item is None:
        raise HTTPException(status_code=404, detail="External field not found")
    return item


@app.delete("/api/v1/external-fields/{field_id}", status_code=204)
def delete_external_field(field_id: str) -> Response:
    if not _environment_context().delete_external_field(field_id):
        raise HTTPException(status_code=404, detail="External field not found")
    return Response(status_code=204)


@app.get("/api/v1/missions/{mission_id}/environment")
def get_mission_environment(mission_id: str) -> dict[str, Any]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    snapshot = _environment_context().get_mission_environment(mission_id)
    if snapshot is None:
        return {
            "mission_id": mission_id,
            "scenario_id": None,
            "obstacles": [],
            "constraints": [],
            "external_fields": [],
            "legacy": True,
        }
    return snapshot


@app.post("/api/v1/missions/{mission_id}/environment", status_code=201)
async def capture_mission_environment(
    mission_id: str, request: MissionEnvironmentCapture
) -> dict[str, Any]:
    mission = repository.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    existing = _environment_context().get_mission_environment(mission_id)
    if existing is not None:
        return existing
    snapshot = _environment_context().capture_snapshot_payload(
        mission_id=mission_id,
        vehicle_id=mission["vehicle_id"],
        vehicle_type=request.vehicle_type,
        scenario_payload=request.scenario,
        capabilities=request.capabilities,
        vehicle_profile_id=request.vehicle_profile_id,
        effective_parameters=request.effective_parameters,
        random_seed=request.random_seed,
    )
    await _application_log(
        "INFO",
        "ENVIRONMENT",
        "MISSION_ENVIRONMENT_CAPTURED",
        f"Environment snapshot captured for {mission_id}.",
        vehicle_id=mission["vehicle_id"],
        mission_id=mission_id,
        details={
            "scenario_id": snapshot.get("scenario_id"),
            "sha256": snapshot.get("sha256"),
        },
    )
    return snapshot


@app.post("/api/v1/simulation-runs", status_code=201)
async def create_simulation_run(request: SimulationRunCreate) -> dict[str, Any]:
    profile = repository.get_vehicle_profile(request.vehicle_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Vehicle profile not found")
    if not profile["enabled"]:
        raise HTTPException(status_code=409, detail="Vehicle profile is disabled")
    if profile["vehicle_type"] != request.vehicle_type:
        raise HTTPException(
            status_code=422, detail="Vehicle type does not match the selected profile"
        )
    scenario = _environment_context().get_scenario(request.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if not scenario.get("enabled", True):
        raise HTTPException(status_code=409, detail="Scenario is disabled")

    effective_parameters = deep_merge(
        profile["parameters"], request.parameter_overrides
    )
    errors = validate_parameters(request.vehicle_type, effective_parameters)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid effective parameters", "errors": errors},
        )
    existing = repository.get_vehicle(request.vehicle_id)
    if existing and existing["active_mission_id"]:
        raise HTTPException(
            status_code=409, detail="Vehicle already has a running mission"
        )

    mission_id = request.mission_id or _simulation_manager().generated_mission_id(
        request.vehicle_id
    )
    request = request.model_copy(update={"mission_id": mission_id})
    if repository.get_mission(mission_id):
        raise HTTPException(status_code=409, detail="Mission ID already exists")
    mission = repository.create_mission(
        MissionCreate(
            mission_id=mission_id,
            vehicle_id=request.vehicle_id,
            name=f"{scenario['name']} - {request.vehicle_id}",
            scenario_name=scenario["name"],
            description=scenario.get("description", ""),
            metadata={
                "schema_version": "0.5.2",
                "vehicle_type": request.vehicle_type,
                "vehicle_profile_id": request.vehicle_profile_id,
                "effective_parameters": effective_parameters,
                "capabilities": profile.get("capabilities", {}),
                "scenario_id": request.scenario_id,
                "scenario_version": scenario.get("version"),
                "random_seed": request.random_seed,
            },
        )
    )
    snapshot = _environment_context().build_snapshot(
        request.scenario_id,
        mission_id=mission_id,
        vehicle_id=request.vehicle_id,
        vehicle_type=request.vehicle_type,
        capabilities=profile.get("capabilities", {}),
        vehicle_profile_id=request.vehicle_profile_id,
        effective_parameters=effective_parameters,
        random_seed=request.random_seed,
    )
    snapshot_path = (
        PROJECT_DIR
        / "backend"
        / "storage"
        / "simulation-scenarios"
        / f"{mission_id}.json"
    )
    _environment_context().write_scenario_file(
        request.scenario_id, target=snapshot_path, snapshot=snapshot
    )

    try:
        run = _simulation_manager().create(
            request, effective_parameters, scenario_path_override=snapshot_path
        )
    except FileNotFoundError as exc:
        repository.transition_mission(mission_id, "ABORTED")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        try:
            repository.transition_mission(mission_id, "ABORTED")
        except Exception:
            pass
        await _application_log(
            "ERROR",
            "SIMULATION",
            "SIMULATION_START_FAILED",
            "Simulation process could not be started.",
            vehicle_id=request.vehicle_id,
            mission_id=mission_id,
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    await _application_log(
        "INFO",
        "SIMULATION",
        "SIMULATION_RUN_CREATED",
        f"Simulation run {run['run_id']} created.",
        vehicle_id=request.vehicle_id,
        mission_id=run["mission_id"],
        details={
            "profile_id": request.vehicle_profile_id,
            "vehicle_type": request.vehicle_type,
            "launch_process": request.launch_process,
            "scenario_id": request.scenario_id,
            "scenario_version": scenario.get("version"),
            "environment_sha256": snapshot.get("sha256"),
            "obstacles": len(snapshot.get("obstacles", [])),
            "constraints": len(snapshot.get("constraints", [])),
            "external_fields": len(snapshot.get("external_fields", [])),
        },
    )
    await stream_connections.broadcast({"stream_type": "simulation_run", "data": run})
    return run


@app.get("/api/v1/simulation-runs")
def list_simulation_runs(
    limit: int = Query(default=100, ge=1, le=1000)
) -> list[dict[str, Any]]:
    return repository.list_simulation_runs(limit)


@app.get("/api/v1/simulation-runs/{run_id}")
def get_simulation_run(run_id: str) -> dict[str, Any]:
    run = repository.get_simulation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return run


@app.post("/api/v1/simulation-runs/{run_id}/stop")
async def stop_simulation_run(
    run_id: str, request: SimulationRunStopRequest
) -> dict[str, Any]:
    run = _simulation_manager().stop(run_id, request.reason)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    await _application_log(
        "WARNING",
        "SIMULATION",
        "SIMULATION_STOP_REQUESTED",
        f"Stop requested for simulation run {run_id}.",
        vehicle_id=run["vehicle_id"],
        mission_id=run["mission_id"],
        details={"reason": request.reason},
    )
    await stream_connections.broadcast({"stream_type": "simulation_run", "data": run})
    return run


@app.get("/api/v1/simulation-runs/{run_id}/log")
def simulation_run_log(
    run_id: str, lines: int = Query(default=120, ge=1, le=2000)
) -> dict[str, Any]:
    run = repository.get_simulation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    path = Path(run["log_path"]) if run.get("log_path") else None
    if path is None or not path.exists():
        return {"run_id": run_id, "lines": []}
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"run_id": run_id, "lines": content[-lines:]}


@app.post("/api/v1/vehicles", status_code=201)
def create_vehicle(request: VehicleCreate) -> dict[str, Any]:
    try:
        return repository.create_vehicle(request)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Vehicle ID already exists"
        ) from exc


@app.get("/api/v1/vehicles")
def list_vehicles() -> list[dict[str, Any]]:
    return repository.list_vehicles()


@app.get("/api/v1/vehicles/{vehicle_id}")
def get_vehicle(vehicle_id: str) -> dict[str, Any]:
    vehicle = repository.get_vehicle(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@app.post("/api/v1/vehicles/{vehicle_id}/heartbeat", status_code=201)
async def vehicle_heartbeat(
    vehicle_id: str, heartbeat: VehicleHeartbeat
) -> dict[str, Any]:
    if heartbeat.vehicle_id != vehicle_id:
        raise HTTPException(
            status_code=422,
            detail="Path vehicle_id does not match heartbeat vehicle_id",
        )
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    try:
        return await _store_heartbeat(heartbeat, transport="HTTP")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Duplicate heartbeat message_id"
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/vehicles/{vehicle_id}/heartbeats")
def vehicle_heartbeats(
    vehicle_id: str,
    limit: int = Query(default=100, ge=1, le=10_000),
) -> list[dict[str, Any]]:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return repository.heartbeat_history(vehicle_id, limit)


@app.put("/api/v1/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: str, request: VehicleUpdate) -> dict[str, Any]:
    vehicle = repository.update_vehicle(vehicle_id, request)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@app.delete("/api/v1/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: str) -> Response:
    try:
        deleted = repository.delete_vehicle(vehicle_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return Response(status_code=204)


@app.get("/api/v1/vehicles/{vehicle_id}/latest")
def latest_telemetry(vehicle_id: str) -> dict[str, Any]:
    record = repository.latest(vehicle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Vehicle telemetry not found")
    return record


@app.get("/api/v1/vehicles/{vehicle_id}/telemetry")
def telemetry_history(
    vehicle_id: str,
    mission_id: str | None = None,
    limit: int = Query(default=500, ge=1, le=10_000),
) -> list[dict[str, Any]]:
    return repository.history(vehicle_id, mission_id, limit)


# ---------------------------------------------------------------------------
# Sensor registry
# ---------------------------------------------------------------------------
@app.post("/api/v1/vehicles/{vehicle_id}/sensors", status_code=201)
def create_sensor(vehicle_id: str, request: SensorCreate) -> dict[str, Any]:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    try:
        return repository.create_sensor(vehicle_id, request)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Sensor ID already exists") from exc


@app.get("/api/v1/vehicles/{vehicle_id}/sensors")
def vehicle_sensors(vehicle_id: str) -> list[dict[str, Any]]:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return repository.list_sensors(vehicle_id)


@app.get("/api/v1/sensors")
def list_sensors(vehicle_id: str | None = None) -> list[dict[str, Any]]:
    return repository.list_sensors(vehicle_id)


@app.get("/api/v1/sensors/{sensor_id}")
def get_sensor(sensor_id: str) -> dict[str, Any]:
    sensor = repository.get_sensor(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@app.put("/api/v1/sensors/{sensor_id}")
def update_sensor(sensor_id: str, request: SensorUpdate) -> dict[str, Any]:
    sensor = repository.update_sensor(sensor_id, request)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@app.delete("/api/v1/sensors/{sensor_id}", status_code=204)
def delete_sensor(sensor_id: str) -> Response:
    try:
        deleted = repository.delete_sensor(sensor_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return Response(status_code=204)


@app.get("/api/v1/sensors/{sensor_id}/quality")
def sensor_quality(sensor_id: str, mission_id: str | None = None) -> dict[str, Any]:
    summary = repository.sensor_quality_summary(sensor_id, mission_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return summary


@app.get("/api/v1/sensors/{sensor_id}/integrity-metrics")
def sensor_integrity_metrics(
    sensor_id: str, mission_id: str | None = None
) -> dict[str, Any]:
    metrics = repository.sensor_integrity_metrics(sensor_id, mission_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return metrics


# ---------------------------------------------------------------------------
# Telemetry and raw acquisition
# ---------------------------------------------------------------------------
@app.post("/api/v1/telemetry", status_code=201)
async def ingest_telemetry(frame: TelemetryFrame) -> dict[str, Any]:
    try:
        return await _store_telemetry(frame)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Duplicate message_id") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/raw-messages", status_code=201)
async def ingest_raw_message(message: RawSensorMessage) -> dict[str, Any]:
    try:
        return await _store_raw(message, transport="HTTP")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Duplicate message_id") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/raw-messages/batch", status_code=201)
async def ingest_raw_batch(messages: list[RawSensorMessage]) -> dict[str, Any]:
    if len(messages) > 10_000:
        raise HTTPException(
            status_code=413, detail="A batch may contain at most 10,000 messages"
        )
    stored = 0
    normalised = 0
    duplicates = 0
    errors: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        try:
            result = await _store_raw(message, transport="FILE_UPLOAD")
            stored += 1
            if result["normalised_telemetry"] is not None:
                normalised += 1
        except sqlite3.IntegrityError:
            duplicates += 1
        except ValueError as exc:
            errors.append(
                {
                    "index": index,
                    "message_id": str(message.message_id),
                    "error": str(exc),
                }
            )
    return {
        "submitted": len(messages),
        "stored": stored,
        "normalised_telemetry_created": normalised,
        "duplicates": duplicates,
        "errors": errors,
    }


@app.get("/api/v1/raw-messages")
def raw_message_history(
    vehicle_id: str | None = None,
    sensor_id: str | None = None,
    mission_id: str | None = None,
    message_type: RawMessageType | None = None,
    limit: int = Query(default=1000, ge=1, le=100_000),
) -> list[dict[str, Any]]:
    return repository.raw_history(
        vehicle_id, sensor_id, mission_id, message_type, limit
    )


# ---------------------------------------------------------------------------
# Data integrity and alerts
# ---------------------------------------------------------------------------
@app.get("/api/v1/integrity-events")
def list_integrity_events(
    vehicle_id: str | None = None,
    sensor_id: str | None = None,
    mission_id: str | None = None,
    check_type: IntegrityCheckType | None = None,
    severity: EventSeverity | None = None,
    limit: int = Query(default=1000, ge=1, le=100_000),
) -> list[dict[str, Any]]:
    return repository.list_integrity_events(
        vehicle_id=vehicle_id,
        sensor_id=sensor_id,
        mission_id=mission_id,
        check_type=check_type,
        severity=severity,
        limit=limit,
    )


@app.get("/api/v1/integrity-events/{integrity_event_id}")
def get_integrity_event(integrity_event_id: str) -> dict[str, Any]:
    event = repository.get_integrity_event(integrity_event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Integrity event not found")
    return event


@app.get("/api/v1/alerts")
def list_alerts(
    status: AlertStatus | None = None,
    severity: EventSeverity | None = None,
    vehicle_id: str | None = None,
    sensor_id: str | None = None,
    mission_id: str | None = None,
    alert_type: AlertType | None = None,
    limit: int = Query(default=500, ge=1, le=10_000),
) -> list[dict[str, Any]]:
    return repository.list_alerts(
        status=status,
        severity=severity,
        vehicle_id=vehicle_id,
        sensor_id=sensor_id,
        mission_id=mission_id,
        alert_type=alert_type,
        limit=limit,
    )


@app.get("/api/v1/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    alert = repository.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@app.post("/api/v1/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str, request: AlertActionRequest
) -> dict[str, Any]:
    try:
        alert = repository.acknowledge_alert(alert_id, request.actor, request.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await stream_connections.broadcast({"stream_type": "alert", "data": alert})
    return alert


@app.post("/api/v1/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: AlertActionRequest) -> dict[str, Any]:
    alert = repository.resolve_alert(alert_id, request.actor, request.note)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await stream_connections.broadcast({"stream_type": "alert", "data": alert})
    return alert


# ---------------------------------------------------------------------------
# Missions and events
# ---------------------------------------------------------------------------
@app.post("/api/v1/missions", status_code=201)
def create_mission(request: MissionCreate) -> dict[str, Any]:
    if repository.get_vehicle(request.vehicle_id) is None:
        raise HTTPException(
            status_code=404, detail="Register the vehicle before creating a mission"
        )
    try:
        return repository.create_mission(request)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Mission ID already exists"
        ) from exc


@app.get("/api/v1/missions")
def list_missions(
    vehicle_id: str | None = None,
    status: MissionStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return repository.list_missions(vehicle_id, status, limit)


@app.get("/api/v1/missions/{mission_id}")
def get_mission(mission_id: str) -> dict[str, Any]:
    mission = repository.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


def _transition(mission_id: str, target: MissionStatus) -> dict[str, Any]:
    try:
        mission = repository.transition_mission(mission_id, target)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@app.post("/api/v1/missions/{mission_id}/start")
def start_mission(mission_id: str) -> dict[str, Any]:
    return _transition(mission_id, "RUNNING")


@app.post("/api/v1/missions/{mission_id}/complete")
def complete_mission(mission_id: str) -> dict[str, Any]:
    return _transition(mission_id, "COMPLETED")


@app.post("/api/v1/missions/{mission_id}/abort")
def abort_mission(mission_id: str) -> dict[str, Any]:
    return _transition(mission_id, "ABORTED")


@app.get("/api/v1/missions/{mission_id}/telemetry")
def mission_telemetry(
    mission_id: str,
    limit: int = Query(default=10_000, ge=1, le=100_000),
) -> list[dict[str, Any]]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return repository.mission_history(mission_id, limit)


@app.get("/api/v1/missions/{mission_id}/quality")
def mission_quality(mission_id: str) -> dict[str, Any]:
    summary = repository.quality_summary(mission_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return summary


@app.get("/api/v1/missions/{mission_id}/integrity-summary")
def mission_integrity_summary(mission_id: str) -> dict[str, Any]:
    summary = repository.integrity_summary(mission_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return summary


@app.get("/api/v1/missions/{mission_id}/integrity-metrics")
def mission_integrity_metrics(mission_id: str) -> dict[str, Any]:
    metrics = repository.mission_integrity_metrics(mission_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return metrics


@app.get("/api/v1/missions/{mission_id}/obstacle-interactions")
def mission_obstacle_interactions(
    mission_id: str,
    risk_level: str | None = Query(
        default=None, pattern="^(CLEAR|CAUTION|WARNING|CRITICAL|COLLISION)$"
    ),
    limit: int = Query(default=2000, ge=1, le=100000),
) -> list[dict[str, Any]]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _obstacle_interaction_service().list_interactions(
        mission_id=mission_id, risk_level=risk_level, limit=limit
    )


@app.get("/api/v1/missions/{mission_id}/obstacle-summary")
def mission_obstacle_summary(mission_id: str) -> dict[str, Any]:
    summary = _obstacle_interaction_service().mission_summary(mission_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return summary


@app.get("/api/v1/vehicles/{vehicle_id}/obstacle-status")
def vehicle_obstacle_status(vehicle_id: str) -> dict[str, Any]:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    record = _obstacle_interaction_service().latest_vehicle_status(vehicle_id)
    return record or {
        "vehicle_id": vehicle_id,
        "risk_level": "UNKNOWN",
        "avoidance_active": False,
        "message": "No obstacle interaction samples are available.",
    }


@app.get("/api/v1/missions/{mission_id}/constraint-violations")
def mission_constraint_violations(
    mission_id: str,
    violation_type: str | None = None,
    status: str | None = Query(default=None, pattern="^(OPEN|ONGOING|RESOLVED)$"),
    limit: int = Query(default=2000, ge=1, le=100000),
) -> list[dict[str, Any]]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _safety_analytics_service().list_violations(
        mission_id, violation_type, status, limit
    )


@app.get("/api/v1/missions/{mission_id}/constraint-summary")
def mission_constraint_summary(mission_id: str) -> dict[str, Any]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _safety_analytics_service().constraint_summary(mission_id)


@app.get("/api/v1/vehicles/{vehicle_id}/constraint-status")
def vehicle_constraint_status(vehicle_id: str) -> dict[str, Any]:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return _safety_analytics_service().vehicle_constraint_status(vehicle_id)


@app.get("/api/v1/missions/{mission_id}/near-misses")
def mission_near_misses(
    mission_id: str,
    classification: str | None = Query(
        default=None, pattern="^(NEAR_MISS|CRITICAL_NEAR_MISS|COLLISION)$"
    ),
    limit: int = Query(default=2000, ge=1, le=100000),
) -> list[dict[str, Any]]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _safety_analytics_service().list_near_misses(
        mission_id, classification, limit
    )


@app.get("/api/v1/missions/{mission_id}/safety-summary")
def mission_safety_summary(mission_id: str) -> dict[str, Any]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _safety_analytics_service().safety_summary(mission_id)


@app.post("/api/v1/missions/{mission_id}/events", status_code=201)
def create_mission_event(
    mission_id: str, request: MissionEventCreate
) -> dict[str, Any]:
    try:
        return repository.create_event(mission_id, request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Event ID already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/missions/{mission_id}/events")
def list_mission_events(mission_id: str) -> list[dict[str, Any]]:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return repository.list_events(mission_id)


@app.get("/api/v1/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    event = repository.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.put("/api/v1/events/{event_id}")
def update_event(event_id: str, request: MissionEventUpdate) -> dict[str, Any]:
    try:
        event = repository.update_event(event_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.delete("/api/v1/events/{event_id}", status_code=204)
def delete_event(event_id: str) -> Response:
    if not repository.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Exports and scenarios
# ---------------------------------------------------------------------------
@app.get("/api/v1/missions/{mission_id}/export")
def export_mission(
    mission_id: str,
    format: Literal["csv", "jsonl"] = "csv",
) -> Response:
    mission = repository.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    records = repository.mission_history(mission_id)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", mission_id)
    if format == "jsonl":
        content = "\n".join(json.dumps(item, separators=(",", ":")) for item in records)
        if content:
            content += "\n"
        return Response(
            content=content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{safe_id}.jsonl"'},
        )
    flattened = repository.flatten_for_csv(records)
    output = io.StringIO(newline="")
    if flattened:
        writer = csv.DictWriter(output, fieldnames=list(flattened[0].keys()))
        writer.writeheader()
        writer.writerows(flattened)
    else:
        output.write("mission_id\n")
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_id}.csv"'},
    )


@app.get("/api/v1/missions/{mission_id}/export/package")
def export_mission_package(mission_id: str) -> Response:
    mission = repository.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    telemetry_records = repository.mission_history(mission_id)
    raw_records = repository.raw_history(mission_id=mission_id, limit=100_000)
    events = repository.list_events(mission_id)
    integrity_events = repository.list_integrity_events(
        mission_id=mission_id, limit=100_000
    )
    alerts = repository.list_alerts(mission_id=mission_id, limit=10_000)
    quality = repository.quality_summary(mission_id) or {}
    integrity_metrics = repository.mission_integrity_metrics(mission_id) or {}
    environment = _environment_context().get_mission_environment(mission_id) or {}
    obstacle_interactions = _obstacle_interaction_service().list_interactions(
        mission_id=mission_id, limit=100000
    )
    obstacle_interactions.reverse()
    constraint_violations = _safety_analytics_service().list_violations(
        mission_id, limit=100000
    )
    constraint_violations.reverse()
    near_misses = _safety_analytics_service().list_near_misses(mission_id, limit=100000)
    near_misses.reverse()
    safety_summary = _safety_analytics_service().safety_summary(mission_id)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", mission_id)

    telemetry_jsonl = "\n".join(
        json.dumps(item, separators=(",", ":")) for item in telemetry_records
    )
    if telemetry_jsonl:
        telemetry_jsonl += "\n"

    telemetry_csv = io.StringIO(newline="")
    flattened = repository.flatten_for_csv(telemetry_records)
    if flattened:
        writer = csv.DictWriter(telemetry_csv, fieldnames=list(flattened[0].keys()))
        writer.writeheader()
        writer.writerows(flattened)
    else:
        telemetry_csv.write("mission_id\n")

    raw_jsonl = "\n".join(
        json.dumps(item, separators=(",", ":")) for item in raw_records
    )
    if raw_jsonl:
        raw_jsonl += "\n"

    raw_fields = [
        "message_id",
        "vehicle_id",
        "sensor_id",
        "mission_id",
        "sequence_no",
        "timestamp_utc",
        "received_at_utc",
        "latency_ms",
        "message_type",
        "transport",
        "topic",
        "valid",
        "confidence",
        "payload_json",
    ]
    raw_csv = io.StringIO(newline="")
    raw_writer = csv.DictWriter(raw_csv, fieldnames=raw_fields)
    raw_writer.writeheader()
    for item in raw_records:
        raw_writer.writerow(
            {
                **{key: item.get(key) for key in raw_fields if key != "payload_json"},
                "valid": item.get("quality", {}).get("valid"),
                "confidence": item.get("quality", {}).get("confidence"),
                "payload_json": json.dumps(
                    item.get("payload", {}), separators=(",", ":")
                ),
            }
        )

    package = io.BytesIO()
    with zipfile.ZipFile(
        package, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("mission.json", json.dumps(mission, indent=2))
        archive.writestr("quality.json", json.dumps(quality, indent=2))
        archive.writestr("events.json", json.dumps(events, indent=2))
        archive.writestr(
            "integrity-events.json", json.dumps(integrity_events, indent=2)
        )
        archive.writestr(
            "integrity-metrics.json", json.dumps(integrity_metrics, indent=2)
        )
        archive.writestr("alerts.json", json.dumps(alerts, indent=2))
        archive.writestr("environment.json", json.dumps(environment, indent=2))
        archive.writestr(
            "obstacle-interactions.json", json.dumps(obstacle_interactions, indent=2)
        )
        archive.writestr(
            "constraint-violations.json", json.dumps(constraint_violations, indent=2)
        )
        archive.writestr("near-misses.json", json.dumps(near_misses, indent=2))
        archive.writestr("safety-summary.json", json.dumps(safety_summary, indent=2))
        archive.writestr("telemetry.csv", telemetry_csv.getvalue())
        archive.writestr("telemetry.jsonl", telemetry_jsonl)
        archive.writestr("raw-messages.csv", raw_csv.getvalue())
        archive.writestr("raw-messages.jsonl", raw_jsonl)

    return Response(
        content=package.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_id}-omip-export.zip"'
        },
    )


@app.get("/api/v1/missions/{mission_id}/raw/export")
def export_raw_mission(
    mission_id: str,
    format: Literal["csv", "jsonl"] = "jsonl",
) -> Response:
    if repository.get_mission(mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    records = repository.raw_history(mission_id=mission_id, limit=100_000)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", mission_id)
    if format == "jsonl":
        content = "\n".join(json.dumps(item, separators=(",", ":")) for item in records)
        if content:
            content += "\n"
        return Response(
            content=content,
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_id}-raw.jsonl"'
            },
        )
    fields = [
        "message_id",
        "vehicle_id",
        "sensor_id",
        "mission_id",
        "sequence_no",
        "timestamp_utc",
        "received_at_utc",
        "latency_ms",
        "message_type",
        "transport",
        "topic",
        "valid",
        "confidence",
        "payload_json",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in records:
        writer.writerow(
            {
                **{key: item.get(key) for key in fields if key != "payload_json"},
                "valid": item.get("quality", {}).get("valid"),
                "confidence": item.get("quality", {}).get("confidence"),
                "payload_json": json.dumps(
                    item.get("payload", {}), separators=(",", ":")
                ),
            }
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_id}-raw.csv"'},
    )


async def _websocket_loop(websocket: WebSocket, manager: ConnectionManager) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket) -> None:
    await _websocket_loop(websocket, telemetry_connections)


@app.websocket("/ws/stream")
async def stream_websocket(websocket: WebSocket) -> None:
    await _websocket_loop(websocket, stream_connections)
