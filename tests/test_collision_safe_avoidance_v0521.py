from pathlib import Path
import json
from simulator.multi_sensor_simulator import motion_state, obstacle_center_and_radius, vehicle_safety_radius

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "vehicle_profiles" / "ugv-small-ackermann-v1.json").read_text())

def clearance(state, scenario):
    obstacle = scenario["obstacles"][0]
    ox, oy, oz, radius = obstacle_center_and_radius(obstacle, 10.0)
    safety = vehicle_safety_radius(PROFILE["parameters"], "GROUND_VEHICLE")
    return ((state["x_m"]-ox)**2 + (state["y_m"]-oy)**2)**0.5 - radius - safety

def test_large_obstacle_never_returns_inside_safety_envelope():
    scenario = json.loads((ROOT / "scenarios" / "ugv_large_obstacle_safe_stop.json").read_text())
    for t in [i * 0.25 for i in range(121)]:
        state = motion_state(t, scenario, "GROUND_VEHICLE", PROFILE["parameters"])
        assert clearance(state, scenario) >= -1e-6

def test_two_obstacles_selects_a_safe_direction():
    scenario = json.loads((ROOT / "scenarios" / "ugv_two_obstacles_direction_choice.json").read_text())
    active = [motion_state(t, scenario, "GROUND_VEHICLE", PROFILE["parameters"]) for t in [8,9,10,11,12]]
    assert any(item["avoidance_active"] for item in active)
    assert any(item["avoidance_direction"] in {"LEFT", "RIGHT", "STOP"} for item in active)

def test_impossible_route_uses_safe_fallback_not_collision():
    scenario = json.loads((ROOT / "scenarios" / "ugv_large_obstacle_safe_stop.json").read_text())
    states = [motion_state(t, scenario, "GROUND_VEHICLE", PROFILE["parameters"]) for t in [6,8,10,12]]
    assert any(item["avoidance_failed"] for item in states)
    assert any(item["fallback_action"] == "EMERGENCY_STOP" for item in states)
