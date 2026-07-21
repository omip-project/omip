from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from app.normalizer import RawMessageNormalizer
from app.system_monitoring import RuntimeMetricsService


def test_system_monitoring_health_logs_and_snapshots(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "system-monitoring.db")
    main.normalizer = RawMessageNormalizer()
    main.runtime_metrics = RuntimeMetricsService()

    with TestClient(main.app) as client:
        health = client.get("/api/v1/system/health")
        assert health.status_code == 200
        body = health.json()
        assert body["overall_status"] in {"HEALTHY", "DEGRADED"}
        assert body["components"]["database"]["status"] == "HEALTHY"
        assert "runtime" in body

        metrics = client.get("/api/v1/system/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["uptime_seconds"] >= 0
        assert "rates" in metrics.json()["runtime"]

        database = client.get("/api/v1/system/database")
        assert database.status_code == 200
        assert database.json()["status"] == "HEALTHY"
        assert "application_logs" in database.json()["table_rows"]

        logs = client.get("/api/v1/system/logs")
        assert logs.status_code == 200
        assert any(item["event_type"] == "SERVICE_START" for item in logs.json())

        # The background monitor writes its first snapshot immediately.
        deadline = time.time() + 1.0
        snapshots = []
        while time.time() < deadline and not snapshots:
            snapshots = client.get("/api/v1/system/metrics/snapshots").json()
            if not snapshots:
                time.sleep(0.02)
        assert snapshots
        assert snapshots[0]["overall_status"] in {"HEALTHY", "DEGRADED"}


def test_platform_alert_api_lifecycle(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "platform-alerts.db")
    main.normalizer = RawMessageNormalizer()
    main.runtime_metrics = RuntimeMetricsService()

    alert = main.repository.upsert_platform_alert(
        active_key="test-database-warning",
        alert_type="DATABASE_WRITE_FAILURE",
        severity="WARNING",
        component="database",
        title="Database write warning",
        description="A simulated database write warning.",
        metadata={"test": True},
    )

    with TestClient(main.app) as client:
        listed = client.get("/api/v1/system/platform-alerts", params={"status": "OPEN"})
        assert listed.status_code == 200
        assert any(item["alert_id"] == alert["alert_id"] for item in listed.json())

        acknowledged = client.post(
            f"/api/v1/system/platform-alerts/{alert['alert_id']}/acknowledge",
            json={"actor": "test-operator", "note": "Reviewing"},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "ACKNOWLEDGED"

        resolved = client.post(
            f"/api/v1/system/platform-alerts/{alert['alert_id']}/resolve",
            json={"actor": "test-operator", "note": "Resolved"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "RESOLVED"
        assert resolved.json()["resolution_source"] == "MANUAL"
