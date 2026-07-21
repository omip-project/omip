from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from app.integrity_service import DataIntegrityService
from app.normalizer import RawMessageNormalizer
from app.schemas import MissionCreate, RawSensorMessage, SensorCreate, VehicleCreate


def configured_repository(path: Path) -> OmipRepository:
    repo = OmipRepository(path)
    repo.create_vehicle(VehicleCreate(vehicle_id="TIME-VEH", vehicle_name="Timing vehicle"))
    repo.create_sensor(
        "TIME-VEH",
        SensorCreate(
            sensor_id="TIME-VEH-GNSS",
            sensor_name="GNSS",
            sensor_type="GNSS",
            sampling_rate_hz=5.0,
        ),
    )
    repo.create_mission(
        MissionCreate(mission_id="TIME-MISSION", vehicle_id="TIME-VEH", name="Timing mission")
    )
    repo.transition_mission("TIME-MISSION", "RUNNING")
    return repo


def raw(sequence_no: int, timestamp: datetime) -> RawSensorMessage:
    return RawSensorMessage(
        schema_version="0.3.1",
        message_id=uuid4(),
        vehicle_id="TIME-VEH",
        sensor_id="TIME-VEH-GNSS",
        mission_id="TIME-MISSION",
        sequence_no=sequence_no,
        timestamp_utc=timestamp,
        message_type="GNSS",
        payload={"x_m": float(sequence_no), "y_m": 0.0, "vx_mps": 1.0, "vy_mps": 0.0},
    )


def test_sampling_rate_finding_uses_registered_expected_rate() -> None:
    now = datetime.now(timezone.utc)
    state = {
        "expected_rate_hz": 5.0,
        "recent_received_at_utc": [
            (now - timedelta(seconds=8)).isoformat(),
            (now - timedelta(seconds=6)).isoformat(),
            (now - timedelta(seconds=4)).isoformat(),
            (now - timedelta(seconds=2)).isoformat(),
        ],
    }
    findings, evaluated = DataIntegrityService._analyse_sampling_rate(
        vehicle_id="TIME-VEH",
        sensor_id="TIME-VEH-GNSS",
        mission_id="TIME-MISSION",
        message_id=str(uuid4()),
        sequence_no=5,
        now=now,
        state=state,
    )
    assert evaluated == {"LOW_SAMPLING_RATE", "HIGH_SAMPLING_RATE"}
    assert len(findings) == 1
    assert findings[0].check_type == "LOW_SAMPLING_RATE"
    assert findings[0].details["expected_rate_hz"] == 5.0
    assert findings[0].details["actual_rate_hz"] < 1.0


def test_timing_api_and_automatic_alert_recovery(tmp_path: Path) -> None:
    main.repository = configured_repository(tmp_path / "timing-api.db")
    main.normalizer = RawMessageNormalizer()

    with TestClient(main.app) as client:
        first_timestamp = datetime.now(timezone.utc)
        first = raw(0, first_timestamp)
        assert client.post("/api/v1/raw-messages", json=first.model_dump(mode="json")).status_code == 201

        delayed = raw(1, datetime.now(timezone.utc) - timedelta(seconds=3))
        response = client.post("/api/v1/raw-messages", json=delayed.model_dump(mode="json"))
        assert response.status_code == 201

        latency_alerts = client.get(
            "/api/v1/alerts",
            params={"mission_id": "TIME-MISSION", "sensor_id": "TIME-VEH-GNSS", "alert_type": "HIGH_LATENCY"},
        ).json()
        assert len(latency_alerts) == 1
        assert latency_alerts[0]["severity"] == "CRITICAL"
        assert latency_alerts[0]["status"] == "OPEN"

        regression_events = client.get(
            "/api/v1/integrity-events",
            params={"mission_id": "TIME-MISSION", "sensor_id": "TIME-VEH-GNSS", "check_type": "TIMESTAMP_REGRESSION"},
        ).json()
        assert len(regression_events) == 1

        healthy = raw(2, datetime.now(timezone.utc))
        assert client.post("/api/v1/raw-messages", json=healthy.model_dump(mode="json")).status_code == 201
        latency_alerts = client.get(
            "/api/v1/alerts",
            params={"mission_id": "TIME-MISSION", "sensor_id": "TIME-VEH-GNSS", "alert_type": "HIGH_LATENCY"},
        ).json()
        assert latency_alerts[0]["status"] == "RESOLVED"
        assert latency_alerts[0]["resolution_source"] == "AUTOMATIC"

        future = raw(3, datetime.now(timezone.utc) + timedelta(seconds=15))
        assert client.post("/api/v1/raw-messages", json=future.model_dump(mode="json")).status_code == 201
        future_events = client.get(
            "/api/v1/integrity-events",
            params={"mission_id": "TIME-MISSION", "sensor_id": "TIME-VEH-GNSS", "check_type": "FUTURE_TIMESTAMP"},
        ).json()
        assert len(future_events) == 1
        assert future_events[0]["severity"] == "CRITICAL"

        sensor_metrics = client.get(
            "/api/v1/sensors/TIME-VEH-GNSS/integrity-metrics",
            params={"mission_id": "TIME-MISSION"},
        )
        assert sensor_metrics.status_code == 200
        assert sensor_metrics.json()["received_messages"] == 4
        assert sensor_metrics.json()["p95_latency_ms"] is not None
        assert sensor_metrics.json()["timestamp_regressions"] >= 1

        mission_metrics = client.get("/api/v1/missions/TIME-MISSION/integrity-metrics")
        assert mission_metrics.status_code == 200
        assert mission_metrics.json()["sensor_count"] == 1
        assert mission_metrics.json()["summary"]["received_messages"] == 4
