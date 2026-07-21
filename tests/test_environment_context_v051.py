from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from simulator.multi_sensor_simulator import motion_state


def test_environment_crud_snapshot_and_vehicle_filtering(tmp_path: Path) -> None:
    original_scenarios_dir = main.SCENARIOS_DIR
    main.SCENARIOS_DIR = tmp_path / "scenarios"
    main.SCENARIOS_DIR.mkdir()
    main.repository = OmipRepository(tmp_path / "v051.db")
    main._simulation_manager_cache = None
    main._storage_manager_cache = None
    main._environment_context_cache = None

    with TestClient(main.app) as client:
        created = client.post(
            "/api/v1/scenarios",
            json={
                "scenario_id": "vehicle-filter-test",
                "name": "Vehicle filter test",
                "description": "Checks vehicle-specific environment applicability.",
                "default_duration_s": 30,
                "sensor_rates_hz": {"GNSS": 5, "IMU": 20, "BATTERY": 1, "VEHICLE_STATUS": 2},
                "motion": {"forward_speed_mps": 1.5},
                "obstacles": [
                    {
                        "obstacle_id": "OBS-AUV",
                        "name": "AUV structure",
                        "obstacle_type": "UNDERWATER_STRUCTURE",
                        "geometry": {
                            "geometry_type": "SPHERE",
                            "position": {"x_m": 10, "y_m": 2, "z_m": -15},
                            "radius_m": 2,
                        },
                        "applies_to_vehicle_types": ["AUV"],
                    },
                    {
                        "obstacle_id": "OBS-UGV",
                        "name": "UGV barrier",
                        "geometry": {
                            "geometry_type": "CIRCLE",
                            "position": {"x_m": 8, "y_m": 0, "z_m": 0},
                            "radius_m": 1,
                        },
                        "applies_to_vehicle_types": ["GROUND_VEHICLE"],
                    },
                ],
                "constraints": [
                    {
                        "constraint_id": "CON-DEPTH",
                        "name": "Depth limit",
                        "constraint_type": "MAXIMUM_DEPTH",
                        "value": 25,
                        "unit": "m",
                        "applies_to_vehicle_types": ["AUV"],
                        "required_capabilities": ["supports_depth_control"],
                    }
                ],
                "external_fields": [
                    {
                        "field_id": "FIELD-CURRENT",
                        "name": "Current",
                        "field_type": "OCEAN_CURRENT",
                        "vector": {"x": 0.2, "y": 0.3, "z": 0, "unit": "m/s"},
                        "unit": "m/s",
                        "applies_to_vehicle_types": ["AUV"],
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        assert len(created.json()["obstacles"]) == 2

        run = client.post(
            "/api/v1/simulation-runs",
            json={
                "vehicle_id": "AUV-V051-001",
                "vehicle_type": "AUV",
                "vehicle_profile_id": "auv-research-thruster-v1",
                "scenario_id": "vehicle-filter-test",
                "duration_s": 20,
                "launch_process": False,
            },
        )
        assert run.status_code == 201, run.text
        mission_id = run.json()["mission_id"]

        environment = client.get(f"/api/v1/missions/{mission_id}/environment")
        assert environment.status_code == 200
        snapshot = environment.json()
        assert [item["obstacle_id"] for item in snapshot["obstacles"]] == ["OBS-AUV"]
        assert [item["constraint_id"] for item in snapshot["constraints"]] == ["CON-DEPTH"]
        assert [item["field_id"] for item in snapshot["external_fields"]] == ["FIELD-CURRENT"]
        assert len(snapshot["sha256"]) == 64

    main.SCENARIOS_DIR = original_scenarios_dir
    main._environment_context_cache = None


def test_direct_mission_environment_capture(tmp_path: Path) -> None:
    original_scenarios_dir = main.SCENARIOS_DIR
    main.SCENARIOS_DIR = tmp_path / "scenarios"
    main.SCENARIOS_DIR.mkdir()
    main.repository = OmipRepository(tmp_path / "capture.db")
    main._simulation_manager_cache = None
    main._storage_manager_cache = None
    main._environment_context_cache = None

    with TestClient(main.app) as client:
        assert client.post("/api/v1/vehicles", json={
            "vehicle_id": "CLI-AUV-001", "vehicle_name": "CLI AUV", "vehicle_type": "AUV"
        }).status_code == 201
        assert client.post("/api/v1/missions", json={
            "mission_id": "CLI-MISSION-001", "vehicle_id": "CLI-AUV-001", "name": "CLI mission"
        }).status_code == 201
        capture = client.post("/api/v1/missions/CLI-MISSION-001/environment", json={
            "vehicle_type": "AUV",
            "vehicle_profile_id": "auv-research-thruster-v1",
            "capabilities": {"supports_depth_control": True},
            "effective_parameters": {"operational_limits": {"maximum_depth_m": 300}},
            "random_seed": 9,
            "scenario": {
                "scenario_id": "inline-cli-scenario",
                "name": "Inline CLI scenario",
                "sensor_rates_hz": {"GNSS": 5, "IMU": 20, "BATTERY": 1, "VEHICLE_STATUS": 2},
                "motion": {"forward_speed_mps": 1.2},
                "obstacles": [],
                "constraints": [{
                    "name": "Depth", "constraint_type": "MAXIMUM_DEPTH", "value": 40,
                    "unit": "m", "applies_to_vehicle_types": ["AUV"]
                }],
                "external_fields": []
            }
        })
        assert capture.status_code == 201, capture.text
        assert capture.json()["scenario_id"] == "inline-cli-scenario"
        assert len(capture.json()["constraints"]) == 1
        second = client.post("/api/v1/missions/CLI-MISSION-001/environment", json={
            "vehicle_type": "AUV", "vehicle_profile_id": "auv-research-thruster-v1",
            "scenario": {"scenario_id": "other", "name": "Other"}
        })
        assert second.status_code == 201
        assert second.json()["scenario_id"] == "inline-cli-scenario"

    main.SCENARIOS_DIR = original_scenarios_dir
    main._environment_context_cache = None


def test_environment_fields_and_constraints_change_motion() -> None:
    base = {
        "motion": {"forward_speed_mps": 2.0, "lateral_amplitude_m": 0.0, "vertical_amplitude_m": 10.0},
        "constraints": [],
        "external_fields": [],
    }
    affected = {
        **base,
        "constraints": [
            {"constraint_type": "MAXIMUM_ALTITUDE", "value": 9.0, "enabled": True},
            {"constraint_type": "SPEED_LIMIT", "value": 1.0, "enabled": True},
        ],
        "external_fields": [
            {"field_type": "WIND", "enabled": True, "vector": {"x": 0.4, "y": -0.2, "z": 0.0}}
        ],
    }
    normal = motion_state(10.0, base, "UAV", {"kinematics": {"maximum_speed_mps": 12.0, "maximum_climb_rate_mps": 4.0}})
    modified = motion_state(10.0, affected, "UAV", {"kinematics": {"maximum_speed_mps": 12.0, "maximum_climb_rate_mps": 4.0}})
    assert modified["z_m"] <= 9.0
    assert modified["environment_vx_mps"] == 0.4
    assert modified["environment_vy_mps"] == -0.2
    assert modified["x_m"] < normal["x_m"]
