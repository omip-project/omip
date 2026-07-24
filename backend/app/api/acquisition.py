"""Acquisition runtime status and MQTT control API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter

from ..schemas import MqttControlRequest


class ConnectionCounter(Protocol):
    """Minimal connection-manager contract required by this router."""

    @property
    def count(self) -> int: ...


class MqttRuntime(Protocol):
    """Minimal MQTT runtime contract required by this router."""

    def status(self) -> dict[str, Any]: ...

    async def disable(self) -> dict[str, Any]: ...

    async def enable(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]],
        host: str | None = None,
        port: int | None = None,
        raw_topic: str | None = None,
        telemetry_topic: str | None = None,
        heartbeat_topic: str | None = None,
    ) -> dict[str, Any]: ...


def create_acquisition_router(
    *,
    get_mqtt_runtime: Callable[[], MqttRuntime],
    telemetry_connections: ConnectionCounter,
    stream_connections: ConnectionCounter,
    database_path: Path,
    mqtt_handler: Callable[[str, dict[str, Any]], Awaitable[None]],
    broadcast: Callable[[dict[str, Any]], Awaitable[None]],
) -> APIRouter:
    """Create acquisition status and MQTT runtime-control routes."""

    router = APIRouter(prefix="/api/v1/acquisition", tags=["Acquisition"])

    def status_payload(mqtt: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "http_ingestion": True,
            "mqtt": mqtt if mqtt is not None else get_mqtt_runtime().status(),
            "telemetry_websocket_clients": telemetry_connections.count,
            "stream_websocket_clients": stream_connections.count,
            "database_path": str(database_path),
        }

    @router.get("/status")
    def acquisition_status() -> dict[str, Any]:
        return status_payload()

    @router.put("/mqtt")
    async def configure_mqtt(request: MqttControlRequest) -> dict[str, Any]:
        """Enable, disable or reconfigure the MQTT consumer without restart."""

        mqtt_runtime = get_mqtt_runtime()
        if not request.enabled:
            mqtt = await mqtt_runtime.disable()
        else:
            mqtt = await mqtt_runtime.enable(
                loop=asyncio.get_running_loop(),
                handler=mqtt_handler,
                host=request.host,
                port=request.port,
                raw_topic=request.raw_topic,
                telemetry_topic=request.telemetry_topic,
                heartbeat_topic=request.heartbeat_topic,
            )
        await broadcast({"stream_type": "acquisition_status", "data": {"mqtt": mqtt}})
        return status_payload(mqtt)

    return router
