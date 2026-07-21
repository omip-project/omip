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


def _configured_repository(path: Path) -> OmipRepository:
    repo = OmipRepository(path)
    repo.create_vehicle(VehicleCreate(vehicle_id="INT-VEH", vehicle_name="Integrity vehicle"))
    repo.create_sensor(
        "INT-VEH",
        SensorCreate(
            sensor_id="INT-VEH-GNSS",
            sensor_name="GNSS",
            sensor_type="GNSS",
            sampling_rate_hz=5.0,
        ),
    )
    repo.create_mission(
        MissionCreate(mission_id="INT-MISSION", vehicle_id="INT-VEH", name="Integrity test")
    )
    repo.transition_mission("INT-MISSION", "RUNNING")
    return repo


def _raw(sequence_no: int, *, message_id=None, seconds: float | None = None) -> RawSensorMessage:
    timestamp = datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc) + timedelta(
        seconds=float(sequence_no if seconds is None else seconds)
    )
    return RawSensorMessage(
        schema_version="0.3.1",
        message_id=message_id or uuid4(),
        vehicle_id="INT-VEH",
        sensor_id="INT-VEH-GNSS",
        mission_id="INT-MISSION",
        sequence_no=sequence_no,
        timestamp_utc=timestamp,
        message_type="GNSS",
        payload={"x_m": float(sequence_no), "y_m": 0.0, "vx_mps": 1.0, "vy_mps": 0.0},
    )


def test_integrity_service_detects_gap_duplicate_and_out_of_order(tmp_path: Path) -> None:
    repo = _configured_repository(tmp_path / "integrity.db")
    service = DataIntegrityService(repo)

    first = _raw(0)
    assert service.analyse_raw(first) == []
    repo.insert_raw_message(first)

    gap = _raw(3)
    findings = service.analyse_raw(gap)
    assert len(findings) == 1
    assert findings[0].check_type == "SEQUENCE_GAP"
    assert findings[0].details["missing_count"] == 2
    repo.insert_raw_message(gap)
    recorded = repo.record_integrity_findings(findings)
    assert recorded["integrity_events"][0]["details"]["missing_from"] == 1

    late = _raw(2, seconds=4)
    findings = service.analyse_raw(late)
    assert findings[0].check_type == "OUT_OF_ORDER"
    repo.insert_raw_message(late)
    repo.record_integrity_findings(findings)

    duplicate_sequence = _raw(3, seconds=5)
    findings = service.analyse_raw(duplicate_sequence)
    assert findings[0].check_type == "DUPLICATE_MESSAGE"
    assert findings[0].details["duplicate_kind"] == "SEQUENCE_NUMBER"

    repeated_old_sequence = _raw(2, seconds=5.5)
    findings = service.analyse_raw(repeated_old_sequence)
    assert {finding.check_type for finding in findings} == {"DUPLICATE_MESSAGE", "OUT_OF_ORDER"}

    duplicate_id = _raw(99, message_id=first.message_id, seconds=6)
    findings = service.analyse_raw(duplicate_id)
    assert findings[0].details["duplicate_kind"] == "MESSAGE_ID"

    summary = repo.integrity_summary("INT-MISSION")
    assert summary is not None
    assert summary["by_check_type"]["SEQUENCE_GAP"] == 1
    assert summary["by_check_type"]["OUT_OF_ORDER"] == 1


def test_integrity_api_creates_and_manages_alerts(tmp_path: Path) -> None:
    main.repository = _configured_repository(tmp_path / "integrity-api.db")
    main.normalizer = RawMessageNormalizer()

    with TestClient(main.app) as client:
        first = _raw(0)
        assert client.post("/api/v1/raw-messages", json=first.model_dump(mode="json")).status_code == 201

        gap = _raw(4)
        assert client.post("/api/v1/raw-messages", json=gap.model_dump(mode="json")).status_code == 201

        events = client.get(
            "/api/v1/integrity-events",
            params={"mission_id": "INT-MISSION", "sensor_id": "INT-VEH-GNSS"},
        ).json()
        assert len(events) == 1
        assert events[0]["check_type"] == "SEQUENCE_GAP"
        assert events[0]["details"]["missing_count"] == 3

        alerts = client.get(
            "/api/v1/alerts",
            params={"mission_id": "INT-MISSION", "sensor_id": "INT-VEH-GNSS"},
        ).json()
        assert len(alerts) == 1
        alert_id = alerts[0]["alert_id"]
        assert alerts[0]["status"] == "OPEN"

        acknowledged = client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge",
            json={"actor": "test-operator", "note": "Investigating"},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "ACKNOWLEDGED"
        assert acknowledged.json()["acknowledged_by"] == "test-operator"

        resolved = client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            json={"actor": "test-operator", "note": "Confirmed simulated gap"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "RESOLVED"

        summary = client.get("/api/v1/missions/INT-MISSION/integrity-summary")
        assert summary.status_code == 200
        assert summary.json()["by_check_type"]["SEQUENCE_GAP"] >= 1
        assert summary.json()["alerts_by_status"]["RESOLVED"] == 1

        duplicate_response = client.post(
            "/api/v1/raw-messages", json=first.model_dump(mode="json")
        )
        assert duplicate_response.status_code == 409
        duplicate_events = client.get(
            "/api/v1/integrity-events",
            params={
                "mission_id": "INT-MISSION",
                "sensor_id": "INT-VEH-GNSS",
                "check_type": "DUPLICATE_MESSAGE",
            },
        ).json()
        assert len(duplicate_events) == 1
        assert duplicate_events[0]["details"]["duplicate_kind"] == "MESSAGE_ID"
