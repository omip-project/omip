from __future__ import annotations

import sys
import time
from pathlib import Path

SIMULATOR_DIR = Path(__file__).resolve().parents[1] / "simulator"
sys.path.insert(0, str(SIMULATOR_DIR))

import multi_sensor_simulator as simulator  # noqa: E402


def test_duration_zero_means_continuous() -> None:
    duration, continuous = simulator.resolve_duration(0, 60)
    assert duration == 0
    assert continuous is True
    duration, continuous = simulator.resolve_duration(None, 60)
    assert duration == 60
    assert continuous is False


def test_reliable_publisher_retries_and_recovers(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_request_json(method, url, payload=None, timeout_s=10.0):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OSError("temporary connection failure")
        return 201, {"ok": True}

    monkeypatch.setattr(simulator, "request_json", fake_request_json)
    publisher = simulator.ReliablePublisher(
        "http",
        "http://example.invalid",
        "127.0.0.1",
        1883,
        max_retries=5,
        retry_base_s=0.01,
        max_buffer=10,
        http_timeout_s=0.1,
    )
    publisher.submit_raw(
        {
            "vehicle_id": "V1",
            "sensor_id": "S1",
            "message_id": "M1",
        }
    )
    deadline = time.monotonic() + 2
    while publisher.stats["sent"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    publisher.close(drain_timeout_s=0.5)

    assert publisher.stats["sent"] == 1
    assert publisher.stats["retried"] == 2
    assert publisher.stats["dropped"] == 0
