from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.database import OmipRepository
from app.normalizer import RawMessageNormalizer
from app.schemas import (MissionCreate, MissionEventCreate, RawSensorMessage,
                         SensorCreate, VehicleCreate)


def make_raw(
    sequence_no: int,
    message_type: str = "GNSS",
    sensor_id: str = "VEH-1-GNSS-001",
    payload: dict | None = None,
) -> RawSensorMessage:
    if payload is None:
        payload = {
            "x_m": float(sequence_no),
            "y_m": float(sequence_no) * 0.5,
            "vx_mps": 1.0,
            "vy_mps": 0.5,
        }
    return RawSensorMessage(
        message_id=uuid4(),
        vehicle_id="VEH-1",
        sensor_id=sensor_id,
        mission_id="MISSION-1",
        sequence_no=sequence_no,
        timestamp_utc=datetime.now(timezone.utc) + timedelta(milliseconds=sequence_no),
        message_type=message_type,
        payload=payload,
    )


def configured_repository(path: Path) -> OmipRepository:
    repo = OmipRepository(path)
    repo.create_vehicle(VehicleCreate(vehicle_id="VEH-1", vehicle_name="Test vehicle"))
    repo.create_sensor(
        "VEH-1",
        SensorCreate(
            sensor_id="VEH-1-GNSS-001",
            sensor_name="GNSS",
            sensor_type="GNSS",
            sampling_rate_hz=5.0,
        ),
    )
    repo.create_mission(
        MissionCreate(mission_id="MISSION-1", vehicle_id="VEH-1", name="Test mission")
    )
    repo.transition_mission("MISSION-1", "RUNNING")
    return repo


def test_registry_raw_storage_and_normalised_telemetry(tmp_path: Path) -> None:
    repo = configured_repository(tmp_path / "omip.db")
    raw = make_raw(0)
    stored_raw = repo.insert_raw_message(raw, transport="HTTP")
    telemetry = RawMessageNormalizer().process(raw)
    assert telemetry is not None
    stored_telemetry = repo.insert_telemetry(telemetry)

    assert stored_raw["sensor_id"] == "VEH-1-GNSS-001"
    assert stored_raw["transport"] == "HTTP"
    assert stored_telemetry["position"]["x_m"] == 0.0
    assert repo.get_vehicle("VEH-1")["raw_message_count"] == 1
    assert repo.get_sensor("VEH-1-GNSS-001")["message_count"] == 1
    assert repo.get_mission("MISSION-1")["telemetry_count"] == 1


def test_normalizer_combines_imu_battery_and_status(tmp_path: Path) -> None:
    normalizer = RawMessageNormalizer()
    imu = make_raw(
        0,
        "IMU",
        "VEH-1-IMU-001",
        {"ax_mps2": 0.2, "ay_mps2": 0.1, "az_mps2": 9.8, "heading_deg": 42.0},
    )
    battery = make_raw(
        0,
        "BATTERY",
        "VEH-1-BATTERY-001",
        {"battery_percent": 73.5},
    )
    status = make_raw(
        0,
        "VEHICLE_STATUS",
        "VEH-1-STATUS-001",
        {"operating_mode": "RETURN_TO_BASE", "autonomy_enabled": True},
    )
    assert normalizer.process(imu) is None
    assert normalizer.process(battery) is None
    assert normalizer.process(status) is None
    telemetry = normalizer.process(make_raw(1))
    assert telemetry is not None
    assert telemetry.acceleration.ax_mps2 == pytest.approx(0.2)
    assert telemetry.state.battery_percent == pytest.approx(73.5)
    assert telemetry.state.operating_mode == "RETURN_TO_BASE"
    assert telemetry.orientation.heading_deg == pytest.approx(26.565051, rel=1e-5)


def test_quality_summary_detects_missing_and_out_of_order_frames(
    tmp_path: Path,
) -> None:
    repo = configured_repository(tmp_path / "omip.db")
    normalizer = RawMessageNormalizer()
    for sequence in [0, 1, 4, 3]:
        raw = make_raw(sequence)
        repo.insert_raw_message(raw)
        telemetry = normalizer.process(raw)
        assert telemetry is not None
        repo.insert_telemetry(telemetry)
    summary = repo.quality_summary("MISSION-1")
    assert summary is not None
    assert summary["missing_frames"] == 2
    assert summary["out_of_order_frames"] == 1


def test_event_crud(tmp_path: Path) -> None:
    repo = configured_repository(tmp_path / "omip.db")
    start = datetime.now(timezone.utc)
    event = repo.create_event(
        "MISSION-1",
        MissionEventCreate(
            event_id="EVENT-1",
            vehicle_id="VEH-1",
            event_type="GNSS_DROPOUT",
            start_timestamp_utc=start,
            end_timestamp_utc=start + timedelta(seconds=5),
            severity="WARNING",
            description="Test dropout",
        ),
    )
    assert event["event_type"] == "GNSS_DROPOUT"
    assert len(repo.list_events("MISSION-1")) == 1
    assert repo.delete_event("EVENT-1") is True
    assert repo.get_event("EVENT-1") is None


def test_heartbeat_keeps_vehicle_online_while_sensor_can_be_offline(
    tmp_path: Path,
) -> None:
    from app.schemas import VehicleHeartbeat

    repo = configured_repository(tmp_path / "omip.db")
    now = datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc)
    repo._utc_now = lambda: now  # type: ignore[method-assign]

    raw = make_raw(0)
    raw.timestamp_utc = now
    repo.insert_raw_message(raw)
    repo.insert_heartbeat(
        VehicleHeartbeat(
            message_id=uuid4(),
            vehicle_id="VEH-1",
            mission_id="MISSION-1",
            timestamp_utc=now,
        )
    )
    assert repo.get_vehicle("VEH-1")["connection_status"] == "ONLINE"
    assert repo.get_sensor("VEH-1-GNSS-001")["connection_status"] == "ONLINE"

    now = now + timedelta(seconds=20)
    repo.insert_heartbeat(
        VehicleHeartbeat(
            message_id=uuid4(),
            vehicle_id="VEH-1",
            mission_id="MISSION-1",
            timestamp_utc=now,
        )
    )
    vehicle = repo.get_vehicle("VEH-1")
    sensor = repo.get_sensor("VEH-1-GNSS-001")
    assert vehicle["connection_status"] == "ONLINE"
    assert vehicle["active_mission_id"] == "MISSION-1"
    assert sensor["connection_status"] == "OFFLINE"


def test_completed_mission_changes_vehicle_and_sensor_to_inactive(
    tmp_path: Path,
) -> None:
    from app.schemas import VehicleHeartbeat

    repo = configured_repository(tmp_path / "omip.db")
    now = datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc)
    repo._utc_now = lambda: now  # type: ignore[method-assign]
    repo.insert_heartbeat(
        VehicleHeartbeat(
            message_id=uuid4(),
            vehicle_id="VEH-1",
            mission_id="MISSION-1",
            timestamp_utc=now,
        )
    )
    repo.transition_mission("MISSION-1", "COMPLETED")
    assert repo.get_vehicle("VEH-1")["connection_status"] == "INACTIVE"
    assert repo.get_sensor("VEH-1-GNSS-001")["connection_status"] == "INACTIVE"
