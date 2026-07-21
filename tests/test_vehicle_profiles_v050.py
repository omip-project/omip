from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.database import OmipRepository
from simulator.multi_sensor_simulator import motion_state


def test_vehicle_profile_catalogue_and_simulation_run(tmp_path: Path) -> None:
    main.repository = OmipRepository(tmp_path / "v050.db")
    main._simulation_manager_cache = None
    main._storage_manager_cache = None

    with TestClient(main.app) as client:
        types = client.get("/api/v1/vehicle-types")
        assert types.status_code == 200
        assert {item["vehicle_type"] for item in types.json()} == {
            "GROUND_VEHICLE", "UAV", "AUV", "USV"
        }

        profiles = client.get("/api/v1/vehicle-profiles?enabled_only=true")
        assert profiles.status_code == 200
        assert len(profiles.json()) == 4

        run = client.post(
            "/api/v1/simulation-runs",
            json={
                "vehicle_id": "AUV-TEST-001",
                "vehicle_type": "AUV",
                "vehicle_profile_id": "auv-research-thruster-v1",
                "scenario_id": "multi_sensor_nominal",
                "duration_s": 30,
                "transport": "http",
                "random_seed": 17,
                "parameter_overrides": {
                    "kinematics": {"maximum_speed_mps": 1.75}
                },
                "launch_process": False,
            },
        )
        assert run.status_code == 201
        payload = run.json()
        assert payload["status"] == "QUEUED"
        assert payload["vehicle_type"] == "AUV"
        assert payload["effective_parameters"]["kinematics"]["maximum_speed_mps"] == 1.75
        assert payload["effective_parameters"]["operational_limits"]["maximum_depth_m"] == 300.0

        runs = client.get("/api/v1/simulation-runs")
        assert runs.status_code == 200
        assert runs.json()[0]["run_id"] == payload["run_id"]


def test_vehicle_types_generate_distinct_motion() -> None:
    scenario = {
        "motion": {
            "forward_speed_mps": 2.0,
            "lateral_amplitude_m": 8.0,
            "lateral_period_s": 24.0,
            "secondary_amplitude_m": 1.5,
            "secondary_period_s": 8.0,
            "vertical_amplitude_m": 5.0,
            "vertical_period_s": 30.0,
        }
    }
    ugv = motion_state(7.0, scenario, "GROUND_VEHICLE", {"kinematics": {"maximum_speed_mps": 4.0}})
    usv = motion_state(7.0, scenario, "USV", {"kinematics": {"maximum_speed_mps": 5.0}})
    uav = motion_state(7.0, scenario, "UAV", {"kinematics": {"maximum_speed_mps": 12.0, "maximum_climb_rate_mps": 4.0}})
    auv = motion_state(7.0, scenario, "AUV", {"kinematics": {"maximum_speed_mps": 2.4}, "operational_limits": {"maximum_depth_m": 300.0}})

    assert ugv["z_m"] == 0.0
    assert usv["z_m"] == 0.0
    assert uav["z_m"] > 0.0
    assert auv["z_m"] < 0.0
    assert ugv["y_m"] != usv["y_m"]
