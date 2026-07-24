from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

try:  # Optional at runtime; psutil is included in requirements for normal installs.
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - fallback for constrained environments
    psutil = None


class RuntimeMetricsService:
    """Thread-safe in-memory counters and rolling rates for OMIP operations."""

    RATE_WINDOWS_S = (10, 60, 300)

    def __init__(self) -> None:
        self._started_monotonic = time.monotonic()
        self._started_at_utc = datetime.now(timezone.utc)
        self._lock = threading.RLock()
        self._counters: dict[str, int] = defaultdict(int)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._database_write_latencies_ms: deque[float] = deque(maxlen=2000)
        self._database_query_latencies_ms: deque[float] = deque(maxlen=2000)
        self._process = psutil.Process(os.getpid()) if psutil is not None else None
        if self._process is not None:
            try:
                self._process.cpu_percent(interval=None)
            except Exception:
                self._process = None

    def increment(
        self, name: str, amount: int = 1, *, rate_event: bool = False
    ) -> None:
        now = time.monotonic()
        with self._lock:
            self._counters[name] += int(amount)
            if rate_event:
                events = self._events[name]
                for _ in range(max(0, int(amount))):
                    events.append(now)
                self._prune(events, now, max(self.RATE_WINDOWS_S))

    def record_database_write(self, latency_ms: float, success: bool = True) -> None:
        with self._lock:
            self._database_write_latencies_ms.append(max(0.0, float(latency_ms)))
            self._counters["database_writes"] += 1
            if not success:
                self._counters["database_write_failures"] += 1

    def record_database_query(self, latency_ms: float, success: bool = True) -> None:
        with self._lock:
            self._database_query_latencies_ms.append(max(0.0, float(latency_ms)))
            self._counters["database_queries"] += 1
            if not success:
                self._counters["database_query_failures"] += 1

    @staticmethod
    def _prune(events: deque[float], now: float, window_s: float) -> None:
        cutoff = now - window_s
        while events and events[0] < cutoff:
            events.popleft()

    @staticmethod
    def _average(values: deque[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    @staticmethod
    def _maximum(values: deque[float]) -> float | None:
        return round(max(values), 3) if values else None

    def _rate(self, name: str, window_s: int, now: float) -> float:
        events = self._events.get(name)
        if not events:
            return 0.0
        self._prune(events, now, max(self.RATE_WINDOWS_S))
        count = sum(1 for event_time in events if event_time >= now - window_s)
        return round(count / float(window_s), 3)

    def snapshot(self) -> dict[str, Any]:
        now_mono = time.monotonic()
        uptime_s = max(0.0, now_mono - self._started_monotonic)
        with self._lock:
            counters = dict(self._counters)
            rates = {
                name: {
                    "current_per_second": self._rate(name, 10, now_mono),
                    "one_minute_per_second": self._rate(name, 60, now_mono),
                    "five_minute_per_second": self._rate(name, 300, now_mono),
                }
                for name in (
                    "http_messages_received",
                    "mqtt_messages_received",
                    "raw_messages_received",
                    "telemetry_frames_received",
                    "heartbeats_received",
                    "messages_accepted",
                    "messages_rejected",
                )
            }
            write_avg = self._average(self._database_write_latencies_ms)
            write_max = self._maximum(self._database_write_latencies_ms)
            query_avg = self._average(self._database_query_latencies_ms)
            query_max = self._maximum(self._database_query_latencies_ms)

        memory_mb: float | None = None
        cpu_percent: float | None = None
        if self._process is not None:
            try:
                memory_mb = round(self._process.memory_info().rss / (1024 * 1024), 3)
                cpu_percent = round(float(self._process.cpu_percent(interval=None)), 3)
            except Exception:  # pragma: no cover - platform dependent
                memory_mb = None
                cpu_percent = None

        return {
            "started_at_utc": self._started_at_utc.isoformat(),
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(uptime_s, 3),
            "counters": counters,
            "rates": rates,
            "database": {
                "write_latency_average_ms": write_avg,
                "write_latency_maximum_ms": write_max,
                "query_latency_average_ms": query_avg,
                "query_latency_maximum_ms": query_max,
                "write_failures": counters.get("database_write_failures", 0),
                "query_failures": counters.get("database_query_failures", 0),
            },
            "process": {
                "memory_usage_mb": memory_mb,
                "cpu_percent": cpu_percent,
            },
        }


class SystemHealthService:
    """Builds a single operational-health view from repository and runtime state."""

    def __init__(
        self,
        repository: Any,
        metrics: RuntimeMetricsService,
        mqtt_runtime: Any,
        telemetry_connections: Any,
        stream_connections: Any,
        *,
        memory_warning_mb: float = 1024.0,
        rejection_warning_ratio: float = 0.10,
    ) -> None:
        self.repository = repository
        self.metrics = metrics
        self.mqtt_runtime = mqtt_runtime
        self.telemetry_connections = telemetry_connections
        self.stream_connections = stream_connections
        self.memory_warning_mb = memory_warning_mb
        self.rejection_warning_ratio = rejection_warning_ratio

    @staticmethod
    def _component(status: str, message: str, **details: Any) -> dict[str, Any]:
        return {"status": status, "message": message, **details}

    def health(self) -> dict[str, Any]:
        runtime = self.metrics.snapshot()
        database = self.repository.database_health()
        mqtt = self.mqtt_runtime.status()
        counters = runtime["counters"]
        accepted = int(counters.get("messages_accepted", 0))
        rejected = int(counters.get("messages_rejected", 0))
        total_evaluated = accepted + rejected
        rejection_ratio = (rejected / total_evaluated) if total_evaluated else 0.0
        memory_mb = runtime["process"].get("memory_usage_mb")

        components: dict[str, dict[str, Any]] = {
            "backend": self._component("HEALTHY", "FastAPI service is running"),
            "database": self._component(
                "HEALTHY" if database.get("status") == "HEALTHY" else "UNHEALTHY",
                database.get("message", "SQLite health check completed"),
                response_time_ms=database.get("response_time_ms"),
                size_bytes=database.get("database_size_bytes"),
            ),
            "mqtt": self._component(
                (
                    "HEALTHY"
                    if mqtt.get("connected")
                    else ("DEGRADED" if mqtt.get("enabled") else "UNKNOWN")
                ),
                (
                    f"Connected to {mqtt.get('host')}:{mqtt.get('port')}"
                    if mqtt.get("connected")
                    else (
                        (
                            mqtt.get("last_error")
                            or "MQTT bridge is enabled but not connected"
                        )
                        if mqtt.get("enabled")
                        else "MQTT bridge is disabled"
                    )
                ),
                enabled=bool(mqtt.get("enabled")),
                connected=bool(mqtt.get("connected")),
            ),
            "websocket": self._component(
                "HEALTHY",
                "WebSocket managers are available",
                telemetry_clients=self.telemetry_connections.count,
                stream_clients=self.stream_connections.count,
            ),
            "ingestion": self._component(
                (
                    "DEGRADED"
                    if rejection_ratio >= self.rejection_warning_ratio
                    else "HEALTHY"
                ),
                (
                    f"Rejected message ratio is {rejection_ratio:.1%}"
                    if rejection_ratio >= self.rejection_warning_ratio
                    else "Message ingestion is operating normally"
                ),
                accepted=accepted,
                rejected=rejected,
                rejection_ratio=round(rejection_ratio, 4),
                raw_rate_per_second=runtime["rates"]["raw_messages_received"][
                    "one_minute_per_second"
                ],
                telemetry_rate_per_second=runtime["rates"]["telemetry_frames_received"][
                    "one_minute_per_second"
                ],
            ),
            "integrity_engine": self._component(
                (
                    "UNHEALTHY"
                    if counters.get("integrity_engine_failures", 0)
                    else "HEALTHY"
                ),
                (
                    "Integrity engine failures have been recorded"
                    if counters.get("integrity_engine_failures", 0)
                    else "Integrity checks are operational"
                ),
                failures=int(counters.get("integrity_engine_failures", 0)),
            ),
            "process": self._component(
                (
                    "DEGRADED"
                    if memory_mb is not None and memory_mb >= self.memory_warning_mb
                    else "HEALTHY"
                ),
                (
                    f"Process memory is {memory_mb:.1f} MB"
                    if memory_mb is not None
                    else "Process resource information is unavailable"
                ),
                memory_usage_mb=memory_mb,
                cpu_percent=runtime["process"].get("cpu_percent"),
            ),
        }

        effective_statuses = [
            component["status"]
            for component in components.values()
            if component["status"] != "UNKNOWN"
        ]
        if "UNHEALTHY" in effective_statuses:
            overall = "UNHEALTHY"
        elif "DEGRADED" in effective_statuses:
            overall = "DEGRADED"
        else:
            overall = "HEALTHY"

        vehicles = self.repository.list_vehicles()
        sensors = self.repository.list_sensors()
        open_data_alerts = len(
            self.repository.list_alerts(status="OPEN", limit=100_000)
        )
        open_platform_alerts = len(
            self.repository.list_platform_alerts(status="OPEN", limit=100_000)
        )

        return {
            "overall_status": overall,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": runtime["uptime_seconds"],
            "components": components,
            "operations": {
                "active_vehicles": sum(
                    1
                    for vehicle in vehicles
                    if vehicle.get("connection_status") == "ONLINE"
                    and vehicle.get("active_mission_id")
                ),
                "online_sensors": sum(
                    1
                    for sensor in sensors
                    if sensor.get("connection_status") == "ONLINE"
                ),
                "registered_vehicles": len(vehicles),
                "registered_sensors": len(sensors),
                "open_data_alerts": open_data_alerts,
                "open_platform_alerts": open_platform_alerts,
                "websocket_clients": self.telemetry_connections.count
                + self.stream_connections.count,
            },
            "runtime": runtime,
            "database": database,
            "mqtt": mqtt,
        }
