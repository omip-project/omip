from __future__ import annotations

from datetime import datetime, timezone
import io
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from app.normalizer import RawMessageNormalizer


def test_http_raw_ingestion_creates_normalised_telemetry(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "api.db")
    main.normalizer = RawMessageNormalizer()
    with TestClient(main.app) as client:
        assert client.post(
            "/api/v1/vehicles",
            json={
                "vehicle_id": "API-VEH",
                "vehicle_name": "API vehicle",
                "vehicle_type": "SIMULATED",
            },
        ).status_code == 201
        assert client.post(
            "/api/v1/vehicles/API-VEH/sensors",
            json={
                "sensor_id": "API-VEH-GNSS-001",
                "sensor_name": "GNSS",
                "sensor_type": "GNSS",
                "sampling_rate_hz": 5,
            },
        ).status_code == 201
        assert client.post(
            "/api/v1/missions",
            json={
                "mission_id": "API-MISSION",
                "vehicle_id": "API-VEH",
                "name": "API test mission",
            },
        ).status_code == 201
        assert client.post("/api/v1/missions/API-MISSION/start").status_code == 200

        raw = {
            "schema_version": "0.3",
            "message_id": str(uuid4()),
            "vehicle_id": "API-VEH",
            "sensor_id": "API-VEH-GNSS-001",
            "mission_id": "API-MISSION",
            "sequence_no": 0,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "message_type": "GNSS",
            "payload": {
                "x_m": 12.0,
                "y_m": 4.0,
                "vx_mps": 1.0,
                "vy_mps": 0.0,
            },
        }
        response = client.post("/api/v1/raw-messages", json=raw)
        assert response.status_code == 201
        assert response.json()["normalised_telemetry"]["position"]["x_m"] == 12.0
        assert len(client.get("/api/v1/missions/API-MISSION/telemetry").json()) == 1
        assert len(client.get("/api/v1/raw-messages?mission_id=API-MISSION").json()) == 1
        assert client.get("/api/v1/acquisition/status").status_code == 200

        csv_export = client.get("/api/v1/missions/API-MISSION/export?format=csv")
        assert csv_export.status_code == 200
        assert "x_m" in csv_export.text

        raw_jsonl = client.get("/api/v1/missions/API-MISSION/raw/export?format=jsonl")
        assert raw_jsonl.status_code == 200
        assert '"sensor_id":"API-VEH-GNSS-001"' in raw_jsonl.text

        package_response = client.get("/api/v1/missions/API-MISSION/export/package")
        assert package_response.status_code == 200
        assert package_response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(package_response.content)) as archive:
            assert set(archive.namelist()) == {
                "mission.json",
                "quality.json",
                "events.json",
                "integrity-events.json",
                "integrity-metrics.json",
                "alerts.json",
                "environment.json",
                "obstacle-interactions.json",
                "constraint-violations.json",
                "near-misses.json",
                "safety-summary.json",
                "telemetry.csv",
                "telemetry.jsonl",
                "raw-messages.csv",
                "raw-messages.jsonl",
            }
            assert "API-MISSION" in archive.read("mission.json").decode("utf-8")
            assert "x_m" in archive.read("telemetry.csv").decode("utf-8")


def test_heartbeat_api_and_inactive_status(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "heartbeat-api.db")
    main.normalizer = RawMessageNormalizer()
    with TestClient(main.app) as client:
        assert client.post(
            "/api/v1/vehicles",
            json={"vehicle_id": "HB-VEH", "vehicle_name": "Heartbeat vehicle"},
        ).status_code == 201
        assert client.post(
            "/api/v1/missions",
            json={"mission_id": "HB-MISSION", "vehicle_id": "HB-VEH", "name": "HB test"},
        ).status_code == 201
        assert client.post("/api/v1/missions/HB-MISSION/start").status_code == 200
        heartbeat = {
            "schema_version": "0.3.1",
            "message_id": str(uuid4()),
            "vehicle_id": "HB-VEH",
            "mission_id": "HB-MISSION",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "state": "RUNNING",
        }
        response = client.post("/api/v1/vehicles/HB-VEH/heartbeat", json=heartbeat)
        assert response.status_code == 201
        assert client.get("/api/v1/vehicles/HB-VEH").json()["connection_status"] == "ONLINE"
        assert len(client.get("/api/v1/vehicles/HB-VEH/heartbeats").json()) == 1
        assert client.post("/api/v1/missions/HB-MISSION/complete").status_code == 200
        assert client.get("/api/v1/vehicles/HB-VEH").json()["connection_status"] == "INACTIVE"
