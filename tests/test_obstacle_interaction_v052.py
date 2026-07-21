from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from app.normalizer import RawMessageNormalizer
from simulator.multi_sensor_simulator import motion_state


def _reset_main(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "interaction.db")
    main.normalizer = RawMessageNormalizer()
    main._environment_context_cache = None
    main._obstacle_interaction_cache = None
    main._storage_manager_cache = None
    main._simulation_manager_cache = None


def test_telemetry_creates_obstacle_interaction_and_summary(tmp_path: Path) -> None:
    _reset_main(tmp_path)
    with TestClient(main.app) as client:
        vehicle_id = "UGV-INTERACTION-001"
        mission_id = "MISSION-INTERACTION-001"
        assert client.post(
            "/api/v1/vehicles",
            json={
                "vehicle_id": vehicle_id,
                "vehicle_name": "Interaction test UGV",
                "vehicle_type": "GROUND_VEHICLE",
                "vehicle_profile_id": "ugv-small-ackermann-v1",
                "capabilities": {"supports_autonomous_navigation": True},
                "parameters": {
                    "geometry": {"length_m": 1.6, "width_m": 0.9, "height_m": 0.7, "safety_margin_m": 0.35},
                    "kinematics": {"maximum_speed_mps": 4.0},
                    "operational_limits": {},
                },
            },
        ).status_code == 201
        assert client.post(
            "/api/v1/missions",
            json={"mission_id": mission_id, "vehicle_id": vehicle_id, "name": "Interaction mission"},
        ).status_code == 201
        assert client.post(f"/api/v1/missions/{mission_id}/start").status_code == 200
        environment = {
            "scenario": {
                "scenario_id": "inline-interaction",
                "name": "Inline interaction",
                "default_duration_s": 20,
                "motion": {},
                "obstacle_avoidance": {"enabled": True},
                "sensor_rates_hz": {},
                "quality": {},
                "faults": {},
                "obstacles": [
                    {
                        "obstacle_id": "OBS-NEAR",
                        "name": "Near obstacle",
                        "obstacle_type": "STATIC_OBSTACLE",
                        "geometry": {
                            "geometry_type": "CIRCLE",
                            "position": {"x_m": 10.0, "y_m": 0.0, "z_m": 0.0},
                            "radius_m": 2.0,
                        },
                        "applies_to_vehicle_types": ["GROUND_VEHICLE"],
                    }
                ],
                "constraints": [],
                "external_fields": [],
            },
            "vehicle_type": "GROUND_VEHICLE",
            "vehicle_profile_id": "ugv-small-ackermann-v1",
            "capabilities": {"supports_autonomous_navigation": True},
            "effective_parameters": {
                "geometry": {"length_m": 1.6, "width_m": 0.9, "height_m": 0.7, "safety_margin_m": 0.35},
                "kinematics": {"maximum_speed_mps": 4.0},
                "operational_limits": {},
            },
            "random_seed": 42,
        }
        assert client.post(f"/api/v1/missions/{mission_id}/environment", json=environment).status_code == 201

        telemetry = {
            "schema_version": "0.3.1",
            "message_id": str(uuid4()),
            "vehicle_id": vehicle_id,
            "mission_id": mission_id,
            "sequence_no": 1,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source": "test",
            "coordinate_frame": "LOCAL_ENU",
            "position": {"x_m": 5.0, "y_m": 0.0, "z_m": 0.0},
            "velocity": {"vx_mps": 2.0, "vy_mps": 0.0, "vz_mps": 0.0, "speed_mps": 2.0},
            "acceleration": {"ax_mps2": 0.0, "ay_mps2": 0.0, "az_mps2": 0.0},
            "orientation": {"heading_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0},
            "state": {"battery_percent": 90.0, "operating_mode": "OBSTACLE_AVOIDANCE", "autonomy_enabled": True, "emergency_stop": False},
            "quality": {"valid": True, "position_source": "SIMULATED", "confidence": 1.0},
        }
        assert client.post("/api/v1/telemetry", json=telemetry).status_code == 201
        interactions = client.get(f"/api/v1/missions/{mission_id}/obstacle-interactions").json()
        assert len(interactions) == 1
        assert interactions[0]["obstacle_id"] == "OBS-NEAR"
        assert interactions[0]["avoidance_active"] is True
        assert interactions[0]["risk_level"] in {"WARNING", "CRITICAL", "COLLISION"}
        summary = client.get(f"/api/v1/missions/{mission_id}/obstacle-summary").json()
        assert summary["total_samples"] == 1
        assert summary["avoidance_samples"] == 1
        assert summary["closest_interaction"]["obstacle_id"] == "OBS-NEAR"


def test_vehicle_specific_avoidance_changes_trajectory() -> None:
    root = Path(__file__).resolve().parents[1]
    ugv_scenario = json.loads((root / "scenarios" / "ugv_active_avoidance.json").read_text())
    ugv_profile = json.loads((root / "vehicle_profiles" / "ugv-small-ackermann-v1.json").read_text())
    state = motion_state(12.5, ugv_scenario, "GROUND_VEHICLE", ugv_profile["parameters"])
    assert state["avoidance_active"] is True
    assert abs(float(state["y_m"])) > 0.5
    assert float(state["z_m"]) == 0.0

    uav_scenario = json.loads((root / "scenarios" / "uav_vertical_avoidance.json").read_text())
    uav_profile = json.loads((root / "vehicle_profiles" / "uav-quadrotor-research-v1.json").read_text())
    base_scenario = dict(uav_scenario)
    base_scenario["obstacles"] = []
    avoided = motion_state(13.6, uav_scenario, "UAV", uav_profile["parameters"])
    baseline = motion_state(13.6, base_scenario, "UAV", uav_profile["parameters"])
    assert avoided["avoidance_active"] is True
    assert float(avoided["z_m"]) > float(baseline["z_m"])
