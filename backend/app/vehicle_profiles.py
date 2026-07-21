from __future__ import annotations

from copy import deepcopy
from typing import Any


VEHICLE_PARAMETER_DEFINITIONS: dict[str, dict[str, dict[str, Any]]] = {
    "GROUND_VEHICLE": {
        "geometry.length_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "geometry.width_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "geometry.height_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "geometry.safety_margin_m": {"unit": "m", "type": "number", "minimum": 0.0, "required": True},
        "kinematics.maximum_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.05, "required": True},
        "kinematics.minimum_turning_radius_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "kinematics.maximum_steering_angle_deg": {"unit": "deg", "type": "number", "minimum": 1.0, "maximum": 89.0, "required": True},
        "dynamics.maximum_acceleration_mps2": {"unit": "m/s2", "type": "number", "minimum": 0.01, "required": True},
        "dynamics.maximum_deceleration_mps2": {"unit": "m/s2", "type": "number", "minimum": 0.01, "required": True},
        "energy.battery_capacity_wh": {"unit": "Wh", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.maximum_slope_deg": {"unit": "deg", "type": "number", "minimum": 0.0, "maximum": 90.0, "required": True},
    },
    "UAV": {
        "geometry.length_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.width_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.height_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.safety_margin_m": {"unit": "m", "type": "number", "minimum": 0.0, "required": True},
        "kinematics.maximum_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.05, "required": True},
        "kinematics.maximum_climb_rate_mps": {"unit": "m/s", "type": "number", "minimum": 0.01, "required": True},
        "kinematics.maximum_descent_rate_mps": {"unit": "m/s", "type": "number", "minimum": 0.01, "required": True},
        "dynamics.maximum_yaw_rate_deg_s": {"unit": "deg/s", "type": "number", "minimum": 0.1, "required": True},
        "energy.battery_capacity_wh": {"unit": "Wh", "type": "number", "minimum": 1.0, "required": True},
        "energy.hover_power_w": {"unit": "W", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.maximum_altitude_m": {"unit": "m", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.maximum_wind_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.0, "required": True},
    },
    "AUV": {
        "geometry.length_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "geometry.width_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.height_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.safety_margin_m": {"unit": "m", "type": "number", "minimum": 0.0, "required": True},
        "kinematics.maximum_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.05, "required": True},
        "kinematics.maximum_ascent_rate_mps": {"unit": "m/s", "type": "number", "minimum": 0.01, "required": True},
        "kinematics.maximum_descent_rate_mps": {"unit": "m/s", "type": "number", "minimum": 0.01, "required": True},
        "dynamics.maximum_pitch_deg": {"unit": "deg", "type": "number", "minimum": 0.0, "maximum": 90.0, "required": True},
        "dynamics.drag_coefficient": {"unit": "", "type": "number", "minimum": 0.0, "required": True},
        "energy.battery_capacity_wh": {"unit": "Wh", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.maximum_depth_m": {"unit": "m", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.minimum_return_battery_percent": {"unit": "%", "type": "number", "minimum": 0.0, "maximum": 100.0, "required": True},
    },
    "USV": {
        "geometry.length_m": {"unit": "m", "type": "number", "minimum": 0.1, "required": True},
        "geometry.width_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.height_m": {"unit": "m", "type": "number", "minimum": 0.05, "required": True},
        "geometry.safety_margin_m": {"unit": "m", "type": "number", "minimum": 0.0, "required": True},
        "geometry.draft_m": {"unit": "m", "type": "number", "minimum": 0.01, "required": True},
        "kinematics.maximum_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.05, "required": True},
        "kinematics.maximum_reverse_speed_mps": {"unit": "m/s", "type": "number", "minimum": 0.0, "required": True},
        "dynamics.maximum_turn_rate_deg_s": {"unit": "deg/s", "type": "number", "minimum": 0.1, "required": True},
        "energy.battery_capacity_wh": {"unit": "Wh", "type": "number", "minimum": 1.0, "required": True},
        "operational_limits.maximum_wave_height_m": {"unit": "m", "type": "number", "minimum": 0.0, "required": True},
    },
}


BUILT_IN_PROFILES: list[dict[str, Any]] = [
    {
        "profile_id": "ugv-small-ackermann-v1",
        "profile_name": "Small Ackermann UGV",
        "vehicle_type": "GROUND_VEHICLE",
        "schema_version": "1.0",
        "description": "Compact research ground vehicle with Ackermann steering.",
        "capabilities": {
            "supports_3d_motion": False,
            "supports_reverse": True,
            "supports_station_keeping": False,
            "supports_depth_control": False,
            "supports_altitude_control": False,
            "supports_autonomous_navigation": True,
        },
        "parameters": {
            "geometry": {"length_m": 1.6, "width_m": 0.9, "height_m": 0.7, "safety_margin_m": 0.35},
            "kinematics": {"maximum_speed_mps": 4.0, "minimum_turning_radius_m": 2.5, "maximum_steering_angle_deg": 32.0},
            "dynamics": {"maximum_acceleration_mps2": 1.8, "maximum_deceleration_mps2": 4.5},
            "energy": {"battery_capacity_wh": 2200.0},
            "operational_limits": {"maximum_slope_deg": 18.0},
        },
    },
    {
        "profile_id": "uav-quadrotor-research-v1",
        "profile_name": "Research Quadrotor UAV",
        "vehicle_type": "UAV",
        "schema_version": "1.0",
        "description": "Four-rotor research UAV with full three-dimensional motion.",
        "capabilities": {
            "supports_3d_motion": True,
            "supports_reverse": True,
            "supports_station_keeping": True,
            "supports_depth_control": False,
            "supports_altitude_control": True,
            "supports_autonomous_navigation": True,
        },
        "parameters": {
            "geometry": {"length_m": 0.65, "width_m": 0.65, "height_m": 0.25, "safety_margin_m": 0.5},
            "kinematics": {"maximum_speed_mps": 12.0, "maximum_climb_rate_mps": 4.0, "maximum_descent_rate_mps": 3.0},
            "dynamics": {"maximum_yaw_rate_deg_s": 90.0},
            "energy": {"battery_capacity_wh": 220.0, "hover_power_w": 420.0},
            "operational_limits": {"maximum_altitude_m": 120.0, "maximum_wind_speed_mps": 10.0},
        },
    },
    {
        "profile_id": "auv-research-thruster-v1",
        "profile_name": "Research Thruster AUV",
        "vehicle_type": "AUV",
        "schema_version": "1.0",
        "description": "Medium research AUV with INS/DVL navigation and thruster propulsion.",
        "capabilities": {
            "supports_3d_motion": True,
            "supports_reverse": True,
            "supports_station_keeping": True,
            "supports_depth_control": True,
            "supports_altitude_control": False,
            "supports_autonomous_navigation": True,
        },
        "parameters": {
            "geometry": {"length_m": 2.2, "width_m": 0.55, "height_m": 0.55, "safety_margin_m": 0.75},
            "kinematics": {"maximum_speed_mps": 2.4, "maximum_ascent_rate_mps": 0.7, "maximum_descent_rate_mps": 0.9},
            "dynamics": {"maximum_pitch_deg": 30.0, "drag_coefficient": 0.42},
            "energy": {"battery_capacity_wh": 5200.0},
            "operational_limits": {"maximum_depth_m": 300.0, "minimum_return_battery_percent": 20.0},
        },
    },
    {
        "profile_id": "usv-small-catamaran-v1",
        "profile_name": "Small Catamaran USV",
        "vehicle_type": "USV",
        "schema_version": "1.0",
        "description": "Small electric catamaran for inland and sheltered-water missions.",
        "capabilities": {
            "supports_3d_motion": False,
            "supports_reverse": True,
            "supports_station_keeping": True,
            "supports_depth_control": False,
            "supports_altitude_control": False,
            "supports_autonomous_navigation": True,
        },
        "parameters": {
            "geometry": {"length_m": 2.4, "width_m": 1.35, "height_m": 0.75, "safety_margin_m": 0.6, "draft_m": 0.25},
            "kinematics": {"maximum_speed_mps": 5.0, "maximum_reverse_speed_mps": 1.2},
            "dynamics": {"maximum_turn_rate_deg_s": 35.0},
            "energy": {"battery_capacity_wh": 4500.0},
            "operational_limits": {"maximum_wave_height_m": 0.8},
        },
    },
]


def deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _get_nested(parameters: dict[str, Any], path: str) -> Any:
    current: Any = parameters
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def validate_parameters(vehicle_type: str, parameters: dict[str, Any]) -> list[str]:
    definitions = VEHICLE_PARAMETER_DEFINITIONS.get(vehicle_type, {})
    errors: list[str] = []
    for path, definition in definitions.items():
        value = _get_nested(parameters, path)
        if value is None:
            if definition.get("required"):
                errors.append(f"Missing required parameter: {path}")
            continue
        if definition.get("type") == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{path} must be numeric")
                continue
            if definition.get("minimum") is not None and float(value) < float(definition["minimum"]):
                errors.append(f"{path} must be >= {definition['minimum']}")
            if definition.get("maximum") is not None and float(value) > float(definition["maximum"]):
                errors.append(f"{path} must be <= {definition['maximum']}")
    return errors


def vehicle_type_catalogue() -> list[dict[str, Any]]:
    labels = {
        "GROUND_VEHICLE": "Ground Vehicle (UGV)",
        "UAV": "Uncrewed Aerial Vehicle (UAV)",
        "AUV": "Autonomous Underwater Vehicle (AUV)",
        "USV": "Uncrewed Surface Vehicle (USV)",
    }
    descriptions = {
        "GROUND_VEHICLE": "Planar Ackermann or differential-drive ground platform.",
        "UAV": "Three-dimensional aerial platform with altitude control.",
        "AUV": "Three-dimensional underwater platform with depth control.",
        "USV": "Surface vessel constrained to the water surface.",
    }
    return [
        {
            "vehicle_type": vehicle_type,
            "label": labels[vehicle_type],
            "description": descriptions[vehicle_type],
            "parameter_definitions": definitions,
        }
        for vehicle_type, definitions in VEHICLE_PARAMETER_DEFINITIONS.items()
    ]
