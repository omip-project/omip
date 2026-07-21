from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MqttBridge:
    """Paho MQTT consumer used by the OMIP acquisition layer.

    The bridge is deliberately independent from FastAPI so it can be started or
    stopped at runtime. Paho is imported lazily, which keeps HTTP-only operation
    available when MQTT is disabled.
    """

    def __init__(
        self,
        host: str,
        port: int,
        raw_topic: str,
        telemetry_topic: str,
        heartbeat_topic: str,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.host = host
        self.port = port
        self.raw_topic = raw_topic
        self.telemetry_topic = telemetry_topic
        self.heartbeat_topic = heartbeat_topic
        self.handler = handler
        self.client: Any | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.connected = False
        self.started = False
        self.last_error: str | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self.started:
            return
        self.loop = loop
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            self.last_error = "paho-mqtt is not installed"
            raise RuntimeError(self.last_error) from exc

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="omip-backend-v043",
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        try:
            # connect_async plus loop_start lets Paho continue retrying when the
            # broker is temporarily unavailable.
            self.client.connect_async(self.host, self.port, keepalive=30)
            self.client.loop_start()
            self.started = True
            self.last_error = None
        except Exception as exc:  # pragma: no cover - network dependent
            self.last_error = str(exc)
            self.client = None
            self.started = False
            raise

    def stop(self) -> None:
        client = self.client
        self.client = None
        self.started = False
        self.connected = False
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:  # pragma: no cover - network dependent
            logger.debug("MQTT disconnect failed", exc_info=True)
        finally:
            try:
                client.loop_stop()
            except Exception:  # pragma: no cover - network dependent
                logger.debug("MQTT loop stop failed", exc_info=True)

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if int(reason_code) == 0:
            self.connected = True
            self.last_error = None
            client.subscribe(
                [
                    (self.raw_topic, 1),
                    (self.telemetry_topic, 1),
                    (self.heartbeat_topic, 1),
                ]
            )
            logger.info("OMIP MQTT bridge connected to %s:%s", self.host, self.port)
        else:  # pragma: no cover - broker dependent
            self.connected = False
            self.last_error = f"MQTT connection rejected: {reason_code}"
            logger.error(self.last_error)

    def _on_disconnect(
        self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any
    ) -> None:
        self.connected = False
        if self.started and int(reason_code) != 0:
            self.last_error = f"MQTT disconnected: {reason_code}"
            logger.warning(self.last_error)

    def _on_message(self, client: Any, userdata: Any, mqtt_message: Any) -> None:
        if self.loop is None:
            return
        try:
            payload = json.loads(mqtt_message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.last_error = f"Invalid MQTT payload on {mqtt_message.topic}: {exc}"
            logger.warning(self.last_error)
            return
        future = asyncio.run_coroutine_threadsafe(
            self.handler(str(mqtt_message.topic), payload), self.loop
        )

        def _log_failure(done: Any) -> None:
            try:
                done.result()
            except Exception as exc:  # pragma: no cover - callback timing dependent
                self.last_error = str(exc)
                logger.exception("MQTT ingestion failed")

        future.add_done_callback(_log_failure)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "started": self.started,
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "raw_topic": self.raw_topic,
            "telemetry_topic": self.telemetry_topic,
            "heartbeat_topic": self.heartbeat_topic,
            "last_error": self.last_error,
        }


class MqttRuntimeManager:
    """Owns the bridge and supports safe runtime enable/disable operations."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        raw_topic: str,
        telemetry_topic: str,
        heartbeat_topic: str,
        bridge_factory: type[MqttBridge] = MqttBridge,
    ) -> None:
        self.host = host
        self.port = port
        self.raw_topic = raw_topic
        self.telemetry_topic = telemetry_topic
        self.heartbeat_topic = heartbeat_topic
        self.bridge_factory = bridge_factory
        self.bridge: MqttBridge | None = None
        self.enabled = False
        self.last_error: str | None = None
        self.last_changed_at_utc: str | None = None
        self._lock = asyncio.Lock()

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
    ) -> dict[str, Any]:
        async with self._lock:
            self.host = host or self.host
            self.port = port or self.port
            self.raw_topic = raw_topic or self.raw_topic
            self.telemetry_topic = telemetry_topic or self.telemetry_topic
            self.heartbeat_topic = heartbeat_topic or self.heartbeat_topic
            if self.bridge is not None:
                self.bridge.stop()
            self.enabled = True
            self.last_error = None
            self.bridge = self.bridge_factory(
                host=self.host,
                port=self.port,
                raw_topic=self.raw_topic,
                telemetry_topic=self.telemetry_topic,
                heartbeat_topic=self.heartbeat_topic,
                handler=handler,
            )
            try:
                self.bridge.start(loop)
            except Exception as exc:
                # Keep the requested state enabled so the dashboard can clearly
                # show WAIT/ERROR and the user can retry without restarting HTTP.
                self.last_error = str(exc)
                self.bridge.last_error = str(exc)
            self.last_changed_at_utc = datetime.now(timezone.utc).isoformat()
            return self.status()

    async def disable(self) -> dict[str, Any]:
        async with self._lock:
            if self.bridge is not None:
                self.bridge.stop()
            self.bridge = None
            self.enabled = False
            self.last_error = None
            self.last_changed_at_utc = datetime.now(timezone.utc).isoformat()
            return self.status()

    def status(self) -> dict[str, Any]:
        if self.bridge is not None:
            status = self.bridge.status()
            if self.last_error and not status.get("last_error"):
                status["last_error"] = self.last_error
        else:
            status = {
                "enabled": self.enabled,
                "started": False,
                "connected": False,
                "host": self.host,
                "port": self.port,
                "raw_topic": self.raw_topic,
                "telemetry_topic": self.telemetry_topic,
                "heartbeat_topic": self.heartbeat_topic,
                "last_error": self.last_error,
            }
        status["enabled"] = self.enabled
        status["last_changed_at_utc"] = self.last_changed_at_utc
        return status
