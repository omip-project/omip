from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from app.normalizer import RawMessageNormalizer
from app.system_monitoring import RuntimeMetricsService


def _raw(sequence: int) -> dict:
    return {
        "schema_version": "0.3.1",
        "message_id": str(uuid4()),
        "vehicle_id": "STORE-VEH",
        "sensor_id": "STORE-GNSS",
        "mission_id": "STORE-MISSION",
        "sequence_no": sequence,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "message_type": "GNSS",
        "payload": {"x_m": float(sequence), "y_m": 1.0, "z_m": 0.25, "vx_mps": 1.0, "vy_mps": 0.0},
    }


def test_storage_summary_pagination_export_backup_and_delete(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "v043.db")
    main.normalizer = RawMessageNormalizer()
    main.runtime_metrics = RuntimeMetricsService()
    main._storage_manager_cache = None

    with TestClient(main.app) as client:
        assert client.post("/api/v1/vehicles", json={"vehicle_id": "STORE-VEH", "vehicle_name": "Storage vehicle"}).status_code == 201
        assert client.post("/api/v1/vehicles/STORE-VEH/sensors", json={
            "sensor_id": "STORE-GNSS", "sensor_name": "GNSS", "sensor_type": "GNSS", "sampling_rate_hz": 5
        }).status_code == 201
        assert client.post("/api/v1/missions", json={
            "mission_id": "STORE-MISSION", "vehicle_id": "STORE-VEH", "name": "Storage mission"
        }).status_code == 201
        assert client.post("/api/v1/missions/STORE-MISSION/start").status_code == 200
        assert client.post("/api/v1/raw-messages", json=_raw(0)).status_code == 201
        assert client.post("/api/v1/raw-messages", json=_raw(1)).status_code == 201
        assert client.post("/api/v1/missions/STORE-MISSION/complete").status_code == 200

        summary = client.get("/api/v1/storage/summary")
        assert summary.status_code == 200
        assert summary.json()["table_rows"]["raw_sensor_messages"] == 2
        assert summary.json()["table_rows"]["telemetry"] == 2

        page = client.get("/api/v1/missions/STORE-MISSION/telemetry/page?page=1&page_size=1")
        assert page.status_code == 200
        assert page.json()["total_items"] == 2
        assert len(page.json()["items"]) == 1

        raw_page = client.get("/api/v1/missions/STORE-MISSION/raw-messages/page?page=2&page_size=1")
        assert raw_page.status_code == 200
        assert raw_page.json()["page"] == 2
        assert raw_page.json()["total_pages"] == 2

        policy = client.put("/api/v1/storage/retention-policy", json={"raw_messages_days": 45})
        assert policy.status_code == 200
        assert policy.json()["raw_messages_days"] == 45
        preview = client.get("/api/v1/storage/cleanup/preview")
        assert preview.status_code == 200
        assert preview.json()["automatic_cleanup_enabled"] is False

        job = client.post("/api/v1/export-jobs", json={
            "mission_id": "STORE-MISSION", "export_format": "package"
        })
        assert job.status_code == 202
        job_id = job.json()["job_id"]
        deadline = time.time() + 5
        current = None
        while time.time() < deadline:
            current = client.get(f"/api/v1/export-jobs/{job_id}").json()
            if current["state"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.05)
        assert current and current["state"] == "COMPLETED"
        download = client.get(f"/api/v1/export-jobs/{job_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"

        backup = client.post("/api/v1/storage/backups", json={"label": "test"})
        assert backup.status_code == 201
        assert backup.json()["state"] == "COMPLETED"
        assert client.get(f"/api/v1/storage/backups/{backup.json()['backup_id']}/download").status_code == 200
        assert client.get("/api/v1/storage/integrity-check").json()["status"] == "OK"

        delete_preview = client.get("/api/v1/missions/STORE-MISSION/delete-preview")
        assert delete_preview.status_code == 200
        assert delete_preview.json()["related_rows"]["raw_sensor_messages"] == 2
        assert client.delete("/api/v1/missions/STORE-MISSION?confirm=wrong").status_code == 409
        deleted = client.delete("/api/v1/missions/STORE-MISSION?confirm=STORE-MISSION")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_rows"]["missions"] == 1
        assert client.get("/api/v1/missions/STORE-MISSION").status_code == 404
