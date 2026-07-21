from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from app.database import OmipRepository
from app.environment_context import EnvironmentContextService
from app.obstacle_interaction import ObstacleInteractionService
from app.safety_analytics import SafetyAnalyticsService


def test_constraint_violation_lifecycle_and_near_miss(tmp_path: Path) -> None:
    repo = OmipRepository(tmp_path / "safety.db")
    env = EnvironmentContextService(repo, tmp_path)
    obstacle = ObstacleInteractionService(repo, env)
    service = SafetyAnalyticsService(repo, env, obstacle)

    # Directly provide a deterministic Mission environment snapshot.
    snapshot = {
        "mission_id": "MISSION-SAFE",
        "scenario_id": "scenario-safe",
        "snapshot_created_at_utc": datetime.now(timezone.utc).isoformat(),
        "vehicle_type": "GROUND_VEHICLE",
        "effective_vehicle_parameters": {
            "geometry": {"length_m": 2.0, "width_m": 1.0, "height_m": 1.0},
            "operational_limits": {"safety_margin_m": 0.5},
        },
        "constraints": [{
            "constraint_id": "SPEED-1",
            "name": "Low speed zone",
            "constraint_type": "SPEED_LIMIT",
            "value": 2.0,
            "unit": "m/s",
            "geometry": {},
        }],
        "obstacles": [],
        "external_fields": [],
    }
    env.capture_snapshot_payload(
        mission_id="MISSION-SAFE",
        vehicle_id="VEH-SAFE",
        vehicle_type="GROUND_VEHICLE",
        scenario_payload=snapshot,
        capabilities={},
        vehicle_profile_id="test-profile",
        effective_parameters=snapshot["effective_vehicle_parameters"],
        random_seed=1,
    )

    base = {
        "message_id": str(uuid4()),
        "vehicle_id": "VEH-SAFE",
        "mission_id": "MISSION-SAFE",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "position": {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0},
        "velocity": {"speed_mps": 3.0},
        "state": {"battery_percent": 90.0},
    }
    result = service.analyse(base)
    assert result["violations"][0]["violation_type"] == "SPEED_LIMIT_VIOLATION"
    assert result["violations"][0]["status"] == "OPEN"

    recovered = dict(base)
    recovered["message_id"] = str(uuid4())
    recovered["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    recovered["velocity"] = {"speed_mps": 1.0}
    result2 = service.analyse(recovered)
    assert result2["resolved"][0]["status"] == "RESOLVED"

    interaction = {
        "interaction_id": "INT-1",
        "obstacle_id": "OBS-1",
        "clearance_m": 0.2,
        "time_to_collision_s": 1.0,
        "closing_speed_mps": 2.0,
        "safety_radius_m": 1.5,
        "risk_level": "CRITICAL",
    }
    near = service.analyse(recovered, interaction)["near_miss"]
    assert near["classification"] == "CRITICAL_NEAR_MISS"
