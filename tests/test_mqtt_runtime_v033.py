from __future__ import annotations

from typing import Any

from app import main
from app.mqtt_bridge import MqttRuntimeManager
from fastapi.testclient import TestClient


class FakeBridge:
    def __init__(
        self,
        host: str,
        port: int,
        raw_topic: str,
        telemetry_topic: str,
        heartbeat_topic: str,
        handler: Any,
    ) -> None:
        self.host = host
        self.port = port
        self.raw_topic = raw_topic
        self.telemetry_topic = telemetry_topic
        self.heartbeat_topic = heartbeat_topic
        self.handler = handler
        self.started = False
        self.connected = False
        self.last_error = None

    def start(self, loop: Any) -> None:
        self.started = True
        self.connected = True

    def stop(self) -> None:
        self.started = False
        self.connected = False

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


def test_runtime_mqtt_enable_disable_api() -> None:
    original = main.mqtt_runtime
    main.mqtt_runtime = MqttRuntimeManager(
        host="127.0.0.1",
        port=1883,
        raw_topic="omip/+/sensors/+",
        telemetry_topic="omip/+/telemetry",
        heartbeat_topic="omip/+/heartbeat",
        bridge_factory=FakeBridge,  # type: ignore[arg-type]
    )
    try:
        with TestClient(main.app) as client:
            response = client.put(
                "/api/v1/acquisition/mqtt",
                json={"enabled": True, "host": "broker.local", "port": 1884},
            )
            assert response.status_code == 200
            mqtt = response.json()["mqtt"]
            assert mqtt["enabled"] is True
            assert mqtt["connected"] is True
            assert mqtt["host"] == "broker.local"
            assert mqtt["port"] == 1884

            response = client.put("/api/v1/acquisition/mqtt", json={"enabled": False})
            assert response.status_code == 200
            mqtt = response.json()["mqtt"]
            assert mqtt["enabled"] is False
            assert mqtt["connected"] is False
    finally:
        main.mqtt_runtime = original


def test_dashboard_uses_global_fleet_totals_and_no_auto_selection() -> None:
    html = main.STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    assert "const vehicles = state.vehicles;" in html
    assert "const sensors = state.sensors;" in html
    assert "state.selectedVehicle = data.vehicle_id" not in html
    assert 'id="mqttToggleBtn"' in html
    assert "/api/v1/acquisition/mqtt" in html
    assert 'id="exportPackage"' in html
    assert "/export/package" in html
    assert 'id="liveZ"' in html
    assert 'id="projectionSelect"' in html
    assert 'id="alertBody"' in html
    assert 'id="integrityBody"' in html
    assert "/api/v1/integrity-events" in html
    assert "/api/v1/alerts" in html


def test_dashboard_mission_selection_is_refresh_safe() -> None:
    html = main.STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    assert 'id="loadMissionBtn"' in html
    assert 'id="missionSelectionState"' in html
    assert "document.activeElement !== missionSelect" in html
    assert "Promise.allSettled" in html
    assert "missionLoadToken" in html
    assert "Loading trajectory preview" in html
    assert "telemetry?limit=20000" in html
    assert "raw-messages?mission_id=${encodeURIComponent(missionId)}&limit=200" in html
