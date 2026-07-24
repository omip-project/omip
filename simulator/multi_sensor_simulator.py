from __future__ import annotations

import argparse
import json
import math
import random
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SENSOR_DEFINITIONS = {
    "GNSS": {
        "sensor_id_suffix": "GNSS-001",
        "unit": "m",
        "coordinate_frame": "LOCAL_ENU",
    },
    "IMU": {"sensor_id_suffix": "IMU-001", "unit": "m/s2", "coordinate_frame": "BODY"},
    "BATTERY": {
        "sensor_id_suffix": "BATTERY-001",
        "unit": "%",
        "coordinate_frame": "VEHICLE",
    },
    "VEHICLE_STATUS": {
        "sensor_id_suffix": "STATUS-001",
        "unit": "state",
        "coordinate_frame": "VEHICLE",
    },
}


class StopRequested(Exception):
    pass


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | list[dict[str, Any]] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        return exc.code, detail


def load_scenario(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("name", path.stem)
    data.setdefault("description", "")
    data.setdefault("default_duration_s", 60)
    data.setdefault(
        "sensor_rates_hz",
        {"GNSS": 5.0, "IMU": 20.0, "BATTERY": 1.0, "VEHICLE_STATUS": 2.0},
    )
    data.setdefault("motion", {})
    data.setdefault("quality", {})
    data.setdefault("faults", {})
    data.setdefault("annotations", [])
    data.setdefault("obstacles", [])
    data.setdefault("constraints", [])
    data.setdefault("external_fields", [])
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def fetch_vehicle_profile(api_base: str, profile_id: str) -> dict[str, Any]:
    status, detail = request_json(
        "GET", f"{api_base.rstrip('/')}/api/v1/vehicle-profiles/{profile_id}"
    )
    if status != 200 or not isinstance(detail, dict):
        raise RuntimeError(f"Vehicle profile load failed ({status}): {detail}")
    return detail


def geometry_contains(
    geometry: dict[str, Any] | None, x: float, y: float, z: float
) -> bool:
    if not geometry:
        return True
    kind = str(geometry.get("geometry_type", "POINT")).upper()
    position = geometry.get("position") or {}
    cx, cy, cz = (
        float(position.get("x_m", 0.0)),
        float(position.get("y_m", 0.0)),
        float(position.get("z_m", 0.0)),
    )
    if kind in {"POINT", "CIRCLE", "SPHERE"}:
        radius = float(geometry.get("radius_m", 0.0) or 0.0)
        if kind == "POINT":
            radius = max(radius, 0.001)
        distance2 = (
            (x - cx) ** 2 + (y - cy) ** 2 + ((z - cz) ** 2 if kind == "SPHERE" else 0.0)
        )
        return distance2 <= radius**2
    if kind == "BOX":
        return (
            abs(x - cx) <= float(geometry.get("length_m", 0.0)) / 2.0
            and abs(y - cy) <= float(geometry.get("width_m", 0.0)) / 2.0
            and abs(z - cz) <= float(geometry.get("height_m", 1e9)) / 2.0
        )
    if kind == "POLYGON":
        points = geometry.get("points") or []
        inside = False
        j = len(points) - 1
        for i, point in enumerate(points):
            xi, yi = float(point.get("x_m", 0.0)), float(point.get("y_m", 0.0))
            xj, yj = float(points[j].get("x_m", 0.0)), float(points[j].get("y_m", 0.0))
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi or 1e-12) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside
    return True


def global_speed_limit(scenario: dict[str, Any], default: float) -> float:
    result = default
    for item in scenario.get("constraints", []):
        if (
            item.get("enabled", True)
            and item.get("constraint_type") == "SPEED_LIMIT"
            and not item.get("geometry")
        ):
            try:
                result = min(result, float(item.get("value")))
            except (TypeError, ValueError):
                pass
    return max(0.0, result)


def environment_vector(
    scenario: dict[str, Any], x: float, y: float, z: float
) -> tuple[float, float, float]:
    vx = vy = vz = 0.0
    for field in scenario.get("external_fields", []):
        if not field.get("enabled", True) or not geometry_contains(
            field.get("geometry"), x, y, z
        ):
            continue
        vector = field.get("vector") or {}
        vx += float(vector.get("x", 0.0))
        vy += float(vector.get("y", 0.0))
        vz += float(vector.get("z", 0.0))
    return vx, vy, vz


def apply_operational_constraints(
    scenario: dict[str, Any], x: float, y: float, z: float
) -> tuple[float, float, float]:
    for item in scenario.get("constraints", []):
        if not item.get("enabled", True) or not geometry_contains(
            item.get("geometry"), x, y, z
        ):
            continue
        kind = item.get("constraint_type")
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        if kind == "MAXIMUM_ALTITUDE":
            z = min(z, value)
        elif kind == "MINIMUM_ALTITUDE":
            z = max(z, value)
        elif kind == "MAXIMUM_DEPTH":
            z = max(z, -abs(value))
        elif kind == "MINIMUM_DEPTH":
            z = min(z, -abs(value))
    return x, y, z


def vehicle_safety_radius(
    parameters: dict[str, Any] | None, vehicle_type: str
) -> float:
    parameters = parameters or {}
    geometry = parameters.get("geometry", {})
    operational = parameters.get("operational_limits", {})
    length = max(0.0, float(geometry.get("length_m", 0.0) or 0.0))
    width = max(0.0, float(geometry.get("width_m", 0.0) or 0.0))
    height = max(0.0, float(geometry.get("height_m", 0.0) or 0.0))
    margin = max(
        0.1,
        float(
            operational.get("safety_margin_m", geometry.get("safety_margin_m", 0.5))
            or 0.5
        ),
    )
    horizontal = 0.5 * math.hypot(length, width)
    if horizontal <= 0.0:
        horizontal = float(operational.get("effective_safety_radius_m", 0.75) or 0.75)
    body = (
        max(horizontal, height * 0.5) if vehicle_type in {"UAV", "AUV"} else horizontal
    )
    return max(0.25, body + margin)


def obstacle_center_and_radius(
    obstacle: dict[str, Any], elapsed_s: float
) -> tuple[float, float, float, float]:
    geometry = obstacle.get("geometry") or {}
    position = geometry.get("position") or {}
    velocity = obstacle.get("velocity") or {}
    x = (
        float(position.get("x_m", 0.0) or 0.0)
        + float(velocity.get("x", 0.0) or 0.0) * elapsed_s
    )
    y = (
        float(position.get("y_m", 0.0) or 0.0)
        + float(velocity.get("y", 0.0) or 0.0) * elapsed_s
    )
    z = (
        float(position.get("z_m", 0.0) or 0.0)
        + float(velocity.get("z", 0.0) or 0.0) * elapsed_s
    )
    kind = str(geometry.get("geometry_type", "POINT")).upper()
    if kind in {"CIRCLE", "SPHERE"}:
        radius = float(geometry.get("radius_m", 0.0) or 0.0)
    elif kind == "BOX":
        radius = 0.5 * math.sqrt(
            float(geometry.get("length_m", 0.0) or 0.0) ** 2
            + float(geometry.get("width_m", 0.0) or 0.0) ** 2
            + float(geometry.get("height_m", 0.0) or 0.0) ** 2
        )
    elif kind == "POLYGON":
        points = geometry.get("points") or []
        if points:
            x = sum(float(point.get("x_m", 0.0) or 0.0) for point in points) / len(
                points
            )
            y = sum(float(point.get("y_m", 0.0) or 0.0) for point in points) / len(
                points
            )
            z = sum(float(point.get("z_m", 0.0) or 0.0) for point in points) / len(
                points
            )
            radius = max(
                math.sqrt(
                    (float(point.get("x_m", 0.0) or 0.0) - x) ** 2
                    + (float(point.get("y_m", 0.0) or 0.0) - y) ** 2
                    + (float(point.get("z_m", 0.0) or 0.0) - z) ** 2
                )
                for point in points
            )
        else:
            radius = 0.0
    else:
        radius = 0.0
    return x, y, z, radius


def _base_position(
    elapsed_s: float,
    scenario: dict[str, Any],
    vehicle_type: str,
    parameters: dict[str, Any],
) -> tuple[float, float, float]:
    motion = scenario.get("motion", {})
    configured_max_speed = float(
        parameters.get("kinematics", {}).get("maximum_speed_mps", 4.0)
    )
    forward_speed = global_speed_limit(
        scenario, min(float(motion.get("forward_speed_mps", 1.4)), configured_max_speed)
    )
    lateral_amplitude = float(motion.get("lateral_amplitude_m", 10.0))
    lateral_period = float(motion.get("lateral_period_s", 24.0))
    secondary_amplitude = float(motion.get("secondary_amplitude_m", 2.0))
    secondary_period = float(motion.get("secondary_period_s", 7.0))
    vertical_amplitude = float(motion.get("vertical_amplitude_m", 0.2))
    vertical_period = float(motion.get("vertical_period_s", 30.0))

    w1 = 2.0 * math.pi / max(lateral_period, 0.1)
    w2 = 2.0 * math.pi / max(secondary_period, 0.1)
    wz = 2.0 * math.pi / max(vertical_period, 0.1)

    if vehicle_type == "UAV":
        climb_limit = float(
            parameters.get("kinematics", {}).get("maximum_climb_rate_mps", 4.0)
        )
        vertical_amplitude = max(
            vertical_amplitude,
            min(12.0, climb_limit * max(vertical_period, 1.0) / (2.0 * math.pi)),
        )
        x = forward_speed * elapsed_s
        y = lateral_amplitude * math.sin(w1 * elapsed_s)
        z = max(0.0, 8.0 + vertical_amplitude * math.sin(wz * elapsed_s))
    elif vehicle_type == "AUV":
        depth_limit = float(
            parameters.get("operational_limits", {}).get("maximum_depth_m", 300.0)
        )
        depth_wave = min(max(vertical_amplitude, 4.0), max(4.0, depth_limit * 0.08))
        x = forward_speed * elapsed_s
        y = lateral_amplitude * math.sin(
            w1 * elapsed_s
        ) + secondary_amplitude * math.sin(w2 * elapsed_s)
        z = -(12.0 + depth_wave * (0.5 + 0.5 * math.sin(wz * elapsed_s)))
    elif vehicle_type == "USV":
        x = forward_speed * elapsed_s
        y = 0.65 * lateral_amplitude * math.sin(w1 * elapsed_s)
        z = 0.0
    else:
        x = forward_speed * elapsed_s
        y = lateral_amplitude * math.sin(
            w1 * elapsed_s
        ) + secondary_amplitude * math.sin(w2 * elapsed_s)
        z = 0.0

    field_vx, field_vy, field_vz = environment_vector(scenario, x, y, z)
    x += field_vx * elapsed_s
    y += field_vy * elapsed_s
    z += field_vz * elapsed_s
    return apply_operational_constraints(scenario, x, y, z)


def _distance_for_vehicle(
    vehicle_type: str, ax: float, ay: float, az: float, bx: float, by: float, bz: float
) -> float:
    if vehicle_type in {"GROUND_VEHICLE", "USV"}:
        return math.hypot(ax - bx, ay - by)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _candidate_is_safe(
    candidate: tuple[float, float, float],
    elapsed_s: float,
    obstacles: list[dict[str, Any]],
    vehicle_type: str,
    safety_radius: float,
    clearance_margin: float,
) -> tuple[bool, float, str | None]:
    x, y, z = candidate
    minimum_clearance = float("inf")
    nearest_id: str | None = None
    for obstacle in obstacles:
        ox, oy, oz, obstacle_radius = obstacle_center_and_radius(obstacle, elapsed_s)
        distance = _distance_for_vehicle(vehicle_type, x, y, z, ox, oy, oz)
        clearance = distance - obstacle_radius - safety_radius
        if clearance < minimum_clearance:
            minimum_clearance = clearance
            nearest_id = str(
                obstacle.get("obstacle_id", obstacle.get("name", "UNKNOWN"))
            )
    return minimum_clearance >= clearance_margin, minimum_clearance, nearest_id


def _avoidance_position(
    elapsed_s: float,
    scenario: dict[str, Any],
    vehicle_type: str,
    parameters: dict[str, Any],
) -> tuple[float, float, float, dict[str, Any]]:
    base_x, base_y, base_z = _base_position(
        elapsed_s, scenario, vehicle_type, parameters
    )
    settings = scenario.get("obstacle_avoidance", {})
    enabled = bool(settings.get("enabled", True))
    obstacles = [
        item for item in scenario.get("obstacles", []) if item.get("enabled", True)
    ]
    safety_radius = vehicle_safety_radius(parameters, vehicle_type)
    empty = {
        "avoidance_active": False,
        "avoidance_failed": False,
        "emergency_stop": False,
        "fallback_action": "NONE",
        "avoidance_direction": "NONE",
        "nearest_obstacle_id": None,
        "clearance_m": None,
        "predicted_minimum_clearance_m": None,
        "required_clearance_m": None,
        "safety_radius_m": safety_radius,
        "avoidance_vector": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    if not enabled or not obstacles:
        return base_x, base_y, base_z, empty

    kinematics = parameters.get("kinematics", {})
    nominal_speed = max(
        0.1,
        min(
            float(scenario.get("motion", {}).get("forward_speed_mps", 1.4)),
            float(kinematics.get("maximum_speed_mps", 4.0)),
        ),
    )
    lookahead_s = max(0.5, float(settings.get("lookahead_s", 6.0) or 6.0))
    clearance_margin = max(
        0.25, float(settings.get("clearance_margin_m", 0.75) or 0.75)
    )
    preferred_max_offset = max(
        1.0,
        float(
            settings.get("maximum_offset_m", safety_radius * 4.0) or safety_radius * 4.0
        ),
    )
    automatic_expansion = bool(settings.get("automatic_offset_expansion", True))
    hard_offset_limit = max(
        preferred_max_offset,
        float(
            settings.get("hard_offset_limit_m", preferred_max_offset * 3.0)
            or preferred_max_offset * 3.0
        ),
    )

    threats: list[dict[str, Any]] = []
    nearest_clearance = float("inf")
    nearest_id: str | None = None
    maximum_required_offset = 0.0
    for obstacle in obstacles:
        ox, oy, oz, obstacle_radius = obstacle_center_and_radius(obstacle, elapsed_s)
        distance = _distance_for_vehicle(
            vehicle_type, base_x, base_y, base_z, ox, oy, oz
        )
        clearance = distance - obstacle_radius - safety_radius
        required = obstacle_radius + safety_radius + clearance_margin
        influence = required + nominal_speed * lookahead_s
        if clearance < nearest_clearance:
            nearest_clearance = clearance
            nearest_id = str(
                obstacle.get("obstacle_id", obstacle.get("name", "UNKNOWN"))
            )
        if distance < influence:
            obstacle_id = str(
                obstacle.get("obstacle_id", obstacle.get("name", "UNKNOWN"))
            )
            threats.append(
                {
                    "id": obstacle_id,
                    "x": ox,
                    "y": oy,
                    "z": oz,
                    "radius": obstacle_radius,
                    "distance": distance,
                    "required": required,
                }
            )
            maximum_required_offset = max(
                maximum_required_offset, required + clearance_margin
            )

    if not threats:
        result = dict(empty)
        result.update(
            {
                "nearest_obstacle_id": nearest_id,
                "clearance_m": (
                    None if nearest_clearance == float("inf") else nearest_clearance
                ),
            }
        )
        return base_x, base_y, base_z, result

    effective_limit = hard_offset_limit if automatic_expansion else preferred_max_offset
    target_offset = min(
        effective_limit, max(preferred_max_offset, maximum_required_offset)
    )
    # Test progressively larger offsets and all vehicle-appropriate directions.
    scales = (0.65, 0.85, 1.0, 1.2, 1.45)
    directions: list[tuple[str, tuple[float, float, float]]]
    if vehicle_type == "UAV":
        directions = [
            ("UP", (0.0, 0.0, 1.0)),
            ("LEFT", (0.0, 1.0, 0.25)),
            ("RIGHT", (0.0, -1.0, 0.25)),
            ("DOWN", (0.0, 0.0, -1.0)),
        ]
    elif vehicle_type == "AUV":
        directions = [
            ("LEFT", (0.0, 1.0, 0.0)),
            ("RIGHT", (0.0, -1.0, 0.0)),
            ("UP", (0.0, 0.0, 1.0)),
            ("DOWN", (0.0, 0.0, -1.0)),
        ]
    else:
        directions = [("LEFT", (0.0, 1.0, 0.0)), ("RIGHT", (0.0, -1.0, 0.0))]

    best = None
    for scale in scales:
        magnitude = min(effective_limit, target_offset * scale)
        for direction_name, vector in directions:
            candidate = (
                base_x + vector[0] * magnitude,
                base_y + vector[1] * magnitude,
                base_z + vector[2] * magnitude,
            )
            candidate = apply_operational_constraints(scenario, *candidate)
            safe, candidate_clearance, candidate_nearest = _candidate_is_safe(
                candidate,
                elapsed_s,
                obstacles,
                vehicle_type,
                safety_radius,
                clearance_margin,
            )
            score = candidate_clearance - 0.03 * magnitude
            if best is None or score > best[0]:
                best = (
                    score,
                    safe,
                    candidate,
                    direction_name,
                    magnitude,
                    candidate_clearance,
                    candidate_nearest,
                )
            if safe:
                x, y, z = candidate
                return (
                    x,
                    y,
                    z,
                    {
                        "avoidance_active": True,
                        "avoidance_failed": False,
                        "emergency_stop": False,
                        "fallback_action": "NONE",
                        "avoidance_direction": direction_name,
                        "nearest_obstacle_id": candidate_nearest or nearest_id,
                        "clearance_m": candidate_clearance,
                        "predicted_minimum_clearance_m": candidate_clearance,
                        "required_clearance_m": clearance_margin,
                        "safety_radius_m": safety_radius,
                        "avoidance_vector": {
                            "x": x - base_x,
                            "y": y - base_y,
                            "z": z - base_z,
                        },
                    },
                )

    # No collision-free candidate exists. Hold before the nearest obstacle instead of crossing it.
    nearest = min(threats, key=lambda item: item["distance"])
    dx, dy, dz = base_x - nearest["x"], base_y - nearest["y"], base_z - nearest["z"]
    raw_distance = _distance_for_vehicle(
        vehicle_type, base_x, base_y, base_z, nearest["x"], nearest["y"], nearest["z"]
    )
    distance = max(1e-6, raw_distance)
    required_distance = nearest["radius"] + safety_radius + clearance_margin
    if raw_distance < 1e-6:
        # At the obstacle centre there is no usable radial direction. Fall back
        # opposite the nominal forward direction instead of returning the centre.
        ux, uy, uz = -1.0, 0.0, 0.0
    elif vehicle_type in {"GROUND_VEHICLE", "USV"}:
        ux, uy, uz = dx / distance, dy / distance, 0.0
    else:
        ux, uy, uz = dx / distance, dy / distance, dz / distance
    hold = (
        nearest["x"] + ux * required_distance,
        nearest["y"] + uy * required_distance,
        nearest["z"] + uz * required_distance,
    )
    hold = apply_operational_constraints(scenario, *hold)
    safe, hold_clearance, hold_nearest = _candidate_is_safe(
        hold, elapsed_s, obstacles, vehicle_type, safety_radius, 0.0
    )
    fallback = "HOLD_POSITION" if vehicle_type in {"UAV", "AUV"} else "EMERGENCY_STOP"
    return (
        hold[0],
        hold[1],
        hold[2],
        {
            "avoidance_active": True,
            "avoidance_failed": True,
            "emergency_stop": True,
            "fallback_action": fallback,
            "avoidance_direction": "STOP",
            "nearest_obstacle_id": hold_nearest or nearest_id,
            "clearance_m": hold_clearance,
            "predicted_minimum_clearance_m": hold_clearance,
            "required_clearance_m": clearance_margin,
            "safety_radius_m": safety_radius,
            "avoidance_vector": {
                "x": hold[0] - base_x,
                "y": hold[1] - base_y,
                "z": hold[2] - base_z,
            },
        },
    )


def motion_state(
    elapsed_s: float,
    scenario: dict[str, Any],
    vehicle_type: str = "GROUND_VEHICLE",
    parameters: dict[str, Any] | None = None,
) -> dict[str, float | bool | str | None | dict[str, float]]:
    parameters = parameters or {}
    x, y, z, interaction = _avoidance_position(
        elapsed_s, scenario, vehicle_type, parameters
    )
    dt = 0.04
    tm = max(0.0, elapsed_s - dt)
    tp = elapsed_s + dt
    xm, ym, zm, _ = _avoidance_position(tm, scenario, vehicle_type, parameters)
    xp, yp, zp, _ = _avoidance_position(tp, scenario, vehicle_type, parameters)
    denom = max(1e-6, tp - tm)
    vx, vy, vz = (xp - xm) / denom, (yp - ym) / denom, (zp - zm) / denom
    if elapsed_s >= dt:
        ax = (xp - 2.0 * x + xm) / (dt * dt)
        ay = (yp - 2.0 * y + ym) / (dt * dt)
        az = (zp - 2.0 * z + zm) / (dt * dt)
    else:
        ax = ay = az = 0.0
    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    heading = math.degrees(math.atan2(vy, vx)) % 360.0
    field_vx, field_vy, field_vz = environment_vector(scenario, x, y, z)
    return {
        "x_m": x,
        "y_m": y,
        "z_m": z,
        "vx_mps": vx,
        "vy_mps": vy,
        "vz_mps": vz,
        "speed_mps": speed,
        "ax_mps2": ax,
        "ay_mps2": ay,
        "az_mps2": az,
        "heading_deg": heading,
        "environment_vx_mps": field_vx,
        "environment_vy_mps": field_vy,
        "environment_vz_mps": field_vz,
        **interaction,
    }


def sensor_id(vehicle_id: str, sensor_type: str) -> str:
    return f"{vehicle_id}-{SENSOR_DEFINITIONS[sensor_type]['sensor_id_suffix']}"


def in_gnss_dropout(elapsed_s: float, faults: dict[str, Any]) -> bool:
    start = faults.get("gnss_dropout_start_s")
    duration = faults.get("gnss_dropout_duration_s")
    if start is None or duration is None:
        return False
    return float(start) <= elapsed_s < float(start) + float(duration)


def build_raw_message(
    vehicle_id: str,
    mission_id: str,
    sensor_type: str,
    sequence_no: int,
    elapsed_s: float,
    wall_start: datetime,
    scenario: dict[str, Any],
    rng: random.Random,
    vehicle_type: str = "GROUND_VEHICLE",
    vehicle_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = motion_state(elapsed_s, scenario, vehicle_type, vehicle_parameters)
    quality_cfg = scenario.get("quality", {})
    faults = scenario.get("faults", {})
    noise_std = float(quality_cfg.get("position_noise_std_m", 0.02))
    confidence = float(quality_cfg.get("confidence", 0.98))
    invalid_every = int(faults.get("invalid_every_n", 0) or 0)
    valid = not (
        invalid_every > 0 and sequence_no > 0 and sequence_no % invalid_every == 0
    )
    timestamp_delay_s = float(faults.get("timestamp_delay_s", 0.0) or 0.0)
    timing_targets = {
        str(item).upper()
        for item in faults.get("timing_fault_sensor_types", SENSOR_DEFINITIONS.keys())
    }
    if sensor_type in timing_targets:
        delay_every = int(faults.get("delay_every_n_messages", 0) or 0)
        if delay_every > 0 and sequence_no > 0 and sequence_no % delay_every == 0:
            timestamp_delay_s += float(faults.get("delay_ms", 0.0) or 0.0) / 1000.0

    timestamp_offset_s = -timestamp_delay_s
    if sensor_type in timing_targets:
        regression_every = int(
            faults.get("timestamp_regression_every_n_messages", 0) or 0
        )
        if (
            regression_every > 0
            and sequence_no > 0
            and sequence_no % regression_every == 0
        ):
            timestamp_offset_s -= (
                float(faults.get("timestamp_regression_ms", 0.0) or 0.0) / 1000.0
            )
        future_every = int(faults.get("future_timestamp_every_n_messages", 0) or 0)
        if future_every > 0 and sequence_no > 0 and sequence_no % future_every == 0:
            timestamp_offset_s += (
                float(faults.get("future_timestamp_ms", 0.0) or 0.0) / 1000.0
            )
    timestamp = wall_start + timedelta(seconds=elapsed_s + timestamp_offset_s)

    if sensor_type == "GNSS":
        payload = {
            "coordinate_frame": "LOCAL_ENU",
            "x_m": state["x_m"] + rng.gauss(0.0, noise_std),
            "y_m": state["y_m"] + rng.gauss(0.0, noise_std),
            "z_m": state["z_m"] + rng.gauss(0.0, noise_std * 0.5),
            "vx_mps": state["vx_mps"],
            "vy_mps": state["vy_mps"],
            "vz_mps": state["vz_mps"],
            "speed_mps": state["speed_mps"],
            "heading_deg": state["heading_deg"],
            "environment_vector_mps": {
                "x": state.get("environment_vx_mps", 0.0),
                "y": state.get("environment_vy_mps", 0.0),
                "z": state.get("environment_vz_mps", 0.0),
            },
            "obstacle_interaction": {
                "avoidance_active": bool(state.get("avoidance_active", False)),
                "nearest_obstacle_id": state.get("nearest_obstacle_id"),
                "clearance_m": state.get("clearance_m"),
                "safety_radius_m": state.get("safety_radius_m"),
                "avoidance_vector": state.get(
                    "avoidance_vector", {"x": 0.0, "y": 0.0, "z": 0.0}
                ),
                "avoidance_failed": bool(state.get("avoidance_failed", False)),
                "emergency_stop": bool(state.get("emergency_stop", False)),
                "fallback_action": state.get("fallback_action", "NONE"),
                "avoidance_direction": state.get("avoidance_direction", "NONE"),
                "predicted_minimum_clearance_m": state.get(
                    "predicted_minimum_clearance_m"
                ),
                "required_clearance_m": state.get("required_clearance_m"),
            },
        }
    elif sensor_type == "IMU":
        spike_every = int(faults.get("imu_noise_spike_every_n", 0) or 0)
        spike = (
            6.0
            if spike_every > 0 and sequence_no > 0 and sequence_no % spike_every == 0
            else 0.0
        )
        payload = {
            "ax_mps2": state["ax_mps2"] + rng.gauss(0.0, 0.01) + spike,
            "ay_mps2": state["ay_mps2"] + rng.gauss(0.0, 0.01),
            "az_mps2": state["az_mps2"] + 9.80665 + rng.gauss(0.0, 0.015),
            "gx_dps": 0.0,
            "gy_dps": 0.0,
            "gz_dps": rng.gauss(0.0, 0.15),
            "heading_deg": state["heading_deg"],
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
        }
    elif sensor_type == "BATTERY":
        drain_per_second = float(
            scenario.get("motion", {}).get("battery_drain_percent_per_s", 0.02)
        )
        payload = {"battery_percent": max(0.0, 100.0 - elapsed_s * drain_per_second)}
    else:
        return_to_base_at = scenario.get("motion", {}).get("return_to_base_at_s")
        if bool(state.get("avoidance_failed", False)):
            mode = (
                "HOLD_POSITION" if vehicle_type in {"UAV", "AUV"} else "EMERGENCY_STOP"
            )
        elif bool(state.get("avoidance_active", False)):
            mode = "OBSTACLE_AVOIDANCE"
        else:
            mode = (
                "RETURN_TO_BASE"
                if return_to_base_at is not None
                and elapsed_s >= float(return_to_base_at)
                else "AUTONOMOUS_MISSION"
            )
        payload = {
            "operating_mode": mode,
            "autonomy_enabled": True,
            "emergency_stop": bool(state.get("emergency_stop", False)),
        }

    reported_sequence = sequence_no
    out_of_order_every = int(faults.get("out_of_order_every_n", 0) or 0)
    if (
        out_of_order_every > 0
        and sequence_no > 2
        and sequence_no % out_of_order_every == 0
    ):
        reported_sequence = sequence_no - 2

    return {
        "schema_version": "0.3.1",
        "message_id": str(uuid4()),
        "vehicle_id": vehicle_id,
        "sensor_id": sensor_id(vehicle_id, sensor_type),
        "mission_id": mission_id,
        "sequence_no": reported_sequence,
        "timestamp_utc": timestamp.isoformat(),
        "message_type": sensor_type,
        "payload": payload,
        "quality": {
            "valid": valid,
            "position_source": "SIMULATED",
            "confidence": max(0.0, min(1.0, confidence if valid else confidence * 0.4)),
        },
    }


class PermanentPublishError(RuntimeError):
    """A message was rejected and should not be retried."""


@dataclass
class PendingPublish:
    kind: str
    payload: dict[str, Any]
    attempts: int = 0
    next_attempt_at: float = field(default_factory=time.monotonic)


class ReliablePublisher:
    """Background publisher with bounded buffering and exponential retry.

    The simulator thread only creates sensor messages. Network I/O happens in a
    worker thread so a temporary backend outage does not freeze the motion clock
    or the per-sensor schedules.
    """

    def __init__(
        self,
        transport: str,
        api_base: str,
        mqtt_host: str,
        mqtt_port: int,
        max_retries: int = 8,
        retry_base_s: float = 0.5,
        max_buffer: int = 10_000,
        http_timeout_s: float = 2.0,
    ) -> None:
        self.transport = transport
        self.api_base = api_base.rstrip("/")
        self.max_retries = max(0, max_retries)
        self.retry_base_s = max(0.05, retry_base_s)
        self.max_buffer = max(1, max_buffer)
        self.http_timeout_s = max(0.1, http_timeout_s)
        self.mqtt_client: Any | None = None
        self._queue: deque[PendingPublish] = deque()
        self._condition = threading.Condition()
        self._closing = False
        self._worker = threading.Thread(
            target=self._run,
            name="omip-reliable-publisher",
            daemon=True,
        )
        self.stats: dict[str, int] = {
            "submitted": 0,
            "sent": 0,
            "failed_attempts": 0,
            "retried": 0,
            "dropped": 0,
            "duplicate_accepted": 0,
            "queue_peak": 0,
        }
        if transport == "mqtt":
            try:
                import paho.mqtt.client as mqtt
            except ImportError as exc:
                raise RuntimeError("MQTT mode requires: pip install paho-mqtt") from exc
            self.mqtt_client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"omip-simulator-v032-{uuid4().hex[:8]}",
            )
            self.mqtt_client.connect(mqtt_host, mqtt_port, keepalive=30)
            self.mqtt_client.loop_start()
        self._worker.start()

    def submit_raw(self, message: dict[str, Any]) -> None:
        self._submit("raw", message)

    def submit_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        self._submit("heartbeat", heartbeat, priority=True)

    def _submit(
        self, kind: str, payload: dict[str, Any], priority: bool = False
    ) -> None:
        item = PendingPublish(kind=kind, payload=payload)
        with self._condition:
            self.stats["submitted"] += 1
            if len(self._queue) >= self.max_buffer:
                self._queue.popleft()
                self.stats["dropped"] += 1
            if priority:
                self._queue.appendleft(item)
            else:
                self._queue.append(item)
            self.stats["queue_peak"] = max(self.stats["queue_peak"], len(self._queue))
            self._condition.notify_all()

    def _http_send(self, item: PendingPublish) -> None:
        if item.kind == "heartbeat":
            vehicle_id = item.payload["vehicle_id"]
            url = f"{self.api_base}/api/v1/vehicles/{vehicle_id}/heartbeat"
        else:
            url = f"{self.api_base}/api/v1/raw-messages"
        status, detail = request_json(
            "POST",
            url,
            item.payload,
            timeout_s=self.http_timeout_s,
        )
        if status in {200, 201, 202}:
            return
        if status == 409:
            # Retried messages are idempotent because message_id is unique.
            self.stats["duplicate_accepted"] += 1
            return
        if 400 <= status < 500:
            raise PermanentPublishError(f"HTTP {status}: {detail}")
        raise RuntimeError(f"HTTP {status}: {detail}")

    def _mqtt_send(self, item: PendingPublish) -> None:
        if self.mqtt_client is None:
            raise RuntimeError("MQTT client is not available")
        vehicle_id = item.payload["vehicle_id"]
        if item.kind == "heartbeat":
            topic = f"omip/{vehicle_id}/heartbeat"
        else:
            topic = f"omip/{vehicle_id}/sensors/{item.payload['sensor_id']}"
        result = self.mqtt_client.publish(topic, json.dumps(item.payload), qos=1)
        if result.rc != 0:
            raise RuntimeError(f"MQTT publish failed with code {result.rc}")
        result.wait_for_publish(timeout=self.http_timeout_s)
        if not result.is_published():
            raise RuntimeError("MQTT publish acknowledgement timed out")

    def _send_once(self, item: PendingPublish) -> None:
        if self.transport == "http":
            self._http_send(item)
        else:
            self._mqtt_send(item)

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._closing:
                    self._condition.wait(timeout=0.5)
                if not self._queue and self._closing:
                    return
                now = time.monotonic()
                due_index = next(
                    (
                        i
                        for i, queued in enumerate(self._queue)
                        if queued.next_attempt_at <= now
                    ),
                    None,
                )
                if due_index is None:
                    wait_s = min(item.next_attempt_at for item in self._queue) - now
                    self._condition.wait(timeout=max(0.01, min(wait_s, 0.5)))
                    continue
                item = self._queue[due_index]
                del self._queue[due_index]
            try:
                self._send_once(item)
                with self._condition:
                    self.stats["sent"] += 1
            except PermanentPublishError as exc:
                with self._condition:
                    self.stats["failed_attempts"] += 1
                    self.stats["dropped"] += 1
                print(f"Publisher dropped invalid message: {exc}", file=sys.stderr)
            except Exception as exc:
                item.attempts += 1
                with self._condition:
                    self.stats["failed_attempts"] += 1
                    if item.attempts > self.max_retries or self._closing:
                        self.stats["dropped"] += 1
                        print(
                            f"Publisher dropped message after {item.attempts} attempts: {exc}",
                            file=sys.stderr,
                        )
                    else:
                        self.stats["retried"] += 1
                        backoff = min(
                            30.0, self.retry_base_s * (2 ** (item.attempts - 1))
                        )
                        item.next_attempt_at = time.monotonic() + backoff
                        self._queue.append(item)
                        self._condition.notify_all()

    def pending_count(self) -> int:
        with self._condition:
            return len(self._queue)

    def close(self, drain_timeout_s: float = 8.0) -> None:
        deadline = time.monotonic() + max(0.0, drain_timeout_s)
        while self.pending_count() and time.monotonic() < deadline:
            time.sleep(0.05)
        with self._condition:
            self._closing = True
            # Messages still buffered after the grace period are explicitly lost.
            if self._queue:
                self.stats["dropped"] += len(self._queue)
                self._queue.clear()
            self._condition.notify_all()
        self._worker.join(timeout=2.0)
        if self.mqtt_client is not None:
            self.mqtt_client.disconnect()
            self.mqtt_client.loop_stop()


def register_platform(
    api_base: str,
    vehicle_id: str,
    mission_id: str,
    scenario: dict[str, Any],
    vehicle_type: str,
    profile: dict[str, Any],
    effective_parameters: dict[str, Any],
    random_seed: int,
    simulation_run_id: str | None = None,
) -> None:
    vehicle = {
        "vehicle_id": vehicle_id,
        "vehicle_name": f"Simulated vehicle {vehicle_id}",
        "vehicle_type": vehicle_type,
        "manufacturer": "OMIP",
        "model": "Multi-Sensor Simulator v0.5.2",
        "description": scenario.get("description", ""),
        "vehicle_profile_id": profile["profile_id"],
        "capabilities": profile.get("capabilities", {}),
        "parameters": effective_parameters,
        "metadata": {
            "simulator": "v0.5.2",
            "profile_name": profile.get("profile_name"),
        },
    }
    status, detail = request_json("POST", f"{api_base}/api/v1/vehicles", vehicle)
    if status == 409:
        status, detail = request_json(
            "PUT",
            f"{api_base}/api/v1/vehicles/{vehicle_id}",
            {
                "vehicle_name": vehicle["vehicle_name"],
                "vehicle_type": vehicle_type,
                "manufacturer": vehicle["manufacturer"],
                "model": vehicle["model"],
                "description": vehicle["description"],
                "vehicle_profile_id": profile["profile_id"],
                "capabilities": profile.get("capabilities", {}),
                "parameters": effective_parameters,
                "metadata": vehicle["metadata"],
            },
        )
    if status not in {200, 201}:
        raise RuntimeError(f"Vehicle registration failed ({status}): {detail}")

    rates = scenario["sensor_rates_hz"]
    for sensor_type, definition in SENSOR_DEFINITIONS.items():
        sensor = {
            "sensor_id": sensor_id(vehicle_id, sensor_type),
            "sensor_name": f"{sensor_type.title()} simulator",
            "sensor_type": sensor_type,
            "manufacturer": "OMIP",
            "model": "Virtual Sensor v0.3.1",
            "unit": definition["unit"],
            "sampling_rate_hz": float(rates.get(sensor_type, 1.0)),
            "coordinate_frame": definition["coordinate_frame"],
            "metadata": {"simulated": True},
        }
        status, detail = request_json(
            "POST", f"{api_base}/api/v1/vehicles/{vehicle_id}/sensors", sensor
        )
        if status not in {201, 409}:
            raise RuntimeError(f"Sensor registration failed ({status}): {detail}")

    mission = {
        "mission_id": mission_id,
        "vehicle_id": vehicle_id,
        "name": f"{scenario['name']} - {vehicle_id}",
        "scenario_name": scenario["name"],
        "description": scenario.get("description", ""),
        "metadata": {
            "transport": "multi-sensor",
            "schema_version": "0.5.2",
            "simulator_version": "0.5.2",
            "simulation_run_id": simulation_run_id,
            "vehicle_type": vehicle_type,
            "vehicle_profile_id": profile["profile_id"],
            "vehicle_profile_version": profile.get("schema_version", "1.0"),
            "effective_parameters": effective_parameters,
            "capabilities": profile.get("capabilities", {}),
            "scenario_id": scenario.get("scenario_id", scenario.get("name")),
            "random_seed": random_seed,
        },
    }
    status, detail = request_json("POST", f"{api_base}/api/v1/missions", mission)
    if status not in {201, 409}:
        raise RuntimeError(f"Mission creation failed ({status}): {detail}")
    status, detail = request_json(
        "POST", f"{api_base}/api/v1/missions/{mission_id}/start"
    )
    if status not in {200, 409}:
        raise RuntimeError(f"Mission start failed ({status}): {detail}")

    environment_capture = {
        "scenario": scenario,
        "vehicle_type": vehicle_type,
        "vehicle_profile_id": profile["profile_id"],
        "capabilities": profile.get("capabilities", {}),
        "effective_parameters": effective_parameters,
        "random_seed": random_seed,
    }
    status, detail = request_json(
        "POST",
        f"{api_base}/api/v1/missions/{mission_id}/environment",
        environment_capture,
    )
    if status not in {200, 201}:
        raise RuntimeError(f"Mission environment capture failed ({status}): {detail}")


def create_annotations(
    api_base: str,
    vehicle_id: str,
    mission_id: str,
    wall_start: datetime,
    scenario: dict[str, Any],
) -> None:
    annotations = list(scenario.get("annotations", []))
    faults = scenario.get("faults", {})
    if (
        faults.get("gnss_dropout_start_s") is not None
        and faults.get("gnss_dropout_duration_s") is not None
    ):
        annotations.append(
            {
                "event_type": "GNSS_DROPOUT",
                "start_s": float(faults["gnss_dropout_start_s"]),
                "end_s": float(faults["gnss_dropout_start_s"])
                + float(faults["gnss_dropout_duration_s"]),
                "severity": "WARNING",
                "description": "GNSS messages intentionally suppressed by the simulator.",
            }
        )
    for annotation in annotations:
        payload = {
            "vehicle_id": vehicle_id,
            "event_type": annotation["event_type"],
            "start_timestamp_utc": (
                wall_start + timedelta(seconds=float(annotation.get("start_s", 0)))
            ).isoformat(),
            "end_timestamp_utc": (
                (wall_start + timedelta(seconds=float(annotation["end_s"]))).isoformat()
                if annotation.get("end_s") is not None
                else None
            ),
            "severity": annotation.get("severity", "INFO"),
            "source": "SIMULATOR",
            "description": annotation.get("description", ""),
            "metadata": annotation.get("metadata", {}),
        }
        status, detail = request_json(
            "POST", f"{api_base}/api/v1/missions/{mission_id}/events", payload
        )
        if status not in {200, 201, 409}:
            print(
                f"Warning: event annotation failed ({status}): {detail}",
                file=sys.stderr,
            )


def resolve_duration(
    requested: float | None, scenario_default: float
) -> tuple[float, bool]:
    duration = float(requested) if requested is not None else float(scenario_default)
    return duration, duration <= 0


def build_heartbeat(
    vehicle_id: str,
    mission_id: str | None,
    state: str,
    pending_messages: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": "0.3.1",
        "message_id": str(uuid4()),
        "vehicle_id": vehicle_id,
        "mission_id": mission_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "source": "multi_sensor_simulator",
        "metadata": {"pending_messages": pending_messages},
    }


def transition_mission_with_retry(
    api_base: str,
    mission_id: str,
    target: str,
    attempts: int = 4,
) -> tuple[int, Any]:
    last_status = 0
    last_detail: Any = "No transition attempt was made"
    for attempt in range(max(1, attempts)):
        try:
            last_status, last_detail = request_json(
                "POST",
                f"{api_base}/api/v1/missions/{mission_id}/{target}",
                timeout_s=3.0,
            )
            if last_status in {200, 409}:
                return last_status, last_detail
            if 400 <= last_status < 500:
                return last_status, last_detail
        except Exception as exc:
            last_status, last_detail = 0, str(exc)
        if attempt + 1 < attempts:
            time.sleep(min(4.0, 0.5 * (2**attempt)))
    return last_status, last_detail


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="OMIP v0.5.2.1 collision-safe multi-sensor simulator"
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--vehicle-id", default="OMIP-SIM-001")
    parser.add_argument(
        "--vehicle-type",
        choices=["GROUND_VEHICLE", "UAV", "AUV", "USV"],
        default="GROUND_VEHICLE",
    )
    parser.add_argument("--vehicle-profile", default="ugv-small-ackermann-v1")
    parser.add_argument(
        "--parameter-overrides",
        default="{}",
        help="JSON object merged over the selected profile parameters",
    )
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--simulation-run-id", default=None)
    parser.add_argument("--mission-id", default=None)
    parser.add_argument(
        "--scenario",
        type=Path,
        default=project_dir / "scenarios" / "multi_sensor_nominal.json",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Run duration in seconds. Use 0 or a negative value for continuous operation.",
    )
    parser.add_argument("--transport", choices=["http", "mqtt"], default="http")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--heartbeat-interval", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=8)
    parser.add_argument("--retry-base", type=float, default=0.5)
    parser.add_argument("--max-buffer", type=int, default=10_000)
    parser.add_argument("--http-timeout", type=float, default=2.0)
    parser.add_argument("--drain-timeout", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    api_base = args.api_base.rstrip("/")
    profile = fetch_vehicle_profile(api_base, args.vehicle_profile)
    if profile.get("vehicle_type") != args.vehicle_type:
        raise RuntimeError(
            f"Profile {args.vehicle_profile} is {profile.get('vehicle_type')}, not {args.vehicle_type}"
        )
    try:
        parameter_overrides = json.loads(args.parameter_overrides or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid --parameter-overrides JSON: {exc}") from exc
    if not isinstance(parameter_overrides, dict):
        raise RuntimeError("--parameter-overrides must be a JSON object")
    effective_parameters = deep_merge(
        profile.get("parameters", {}), parameter_overrides
    )
    duration, continuous = resolve_duration(
        args.duration, float(scenario["default_duration_s"])
    )
    mission_id = args.mission_id or (
        f"MISSION-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-"
        f"{uuid4().hex[:6].upper()}"
    )
    register_platform(
        api_base,
        args.vehicle_id,
        mission_id,
        scenario,
        args.vehicle_type,
        profile,
        effective_parameters,
        args.random_seed,
        args.simulation_run_id,
    )

    wall_start = datetime.now(timezone.utc)
    create_annotations(api_base, args.vehicle_id, mission_id, wall_start, scenario)
    publisher = ReliablePublisher(
        args.transport,
        api_base,
        args.mqtt_host,
        args.mqtt_port,
        max_retries=args.max_retries,
        retry_base_s=args.retry_base,
        max_buffer=args.max_buffer,
        http_timeout_s=args.http_timeout,
    )
    rng = random.Random(args.random_seed)
    configured_rates = {
        key: float(value) for key, value in scenario["sensor_rates_hz"].items()
    }
    faults = scenario.get("faults", {})
    rate_multipliers = {
        str(key).upper(): float(value)
        for key, value in faults.get("sensor_rate_multipliers", {}).items()
    }
    rates = {}
    for sensor_type in SENSOR_DEFINITIONS:
        legacy_key = f"{sensor_type.lower()}_rate_multiplier"
        multiplier = float(
            faults.get(legacy_key, rate_multipliers.get(sensor_type, 1.0)) or 1.0
        )
        rates[sensor_type] = max(
            0.001, configured_rates.get(sensor_type, 1.0) * multiplier
        )
    next_due = {sensor_type: 0.0 for sensor_type in SENSOR_DEFINITIONS}
    sequences = {sensor_type: 0 for sensor_type in SENSOR_DEFINITIONS}
    generated = {sensor_type: 0 for sensor_type in SENSOR_DEFINITIONS}
    fault_dropped = {sensor_type: 0 for sensor_type in SENSOR_DEFINITIONS}
    stop_requested = False

    def _request_stop(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    duration_text = "continuous" if continuous else f"{duration:.1f}s"
    print("OMIP v0.5.2 simulator started")
    print(f"  Vehicle:   {args.vehicle_id}")
    print(f"  Type:      {args.vehicle_type}")
    print(f"  Profile:   {args.vehicle_profile}")
    print(f"  Mission:   {mission_id}")
    print(f"  Scenario:  {scenario['name']}")
    print(f"  Transport: {args.transport.upper()}")
    print(f"  Duration:  {duration_text}")
    print(f"  Heartbeat: every {max(0.2, args.heartbeat_interval):.1f}s")
    print(
        "  Rates:     "
        + ", ".join(f"{name}={rates[name]:.2f}Hz" for name in SENSOR_DEFINITIONS)
    )
    print("  Stop:      Ctrl+C")

    start_mono = time.monotonic()
    next_heartbeat = 0.0
    fatal_error: Exception | None = None
    try:
        while not stop_requested:
            elapsed = time.monotonic() - start_mono
            if not continuous and elapsed >= duration:
                break

            if elapsed + 1e-9 >= next_heartbeat:
                publisher.submit_heartbeat(
                    build_heartbeat(
                        args.vehicle_id,
                        mission_id,
                        "RUNNING",
                        publisher.pending_count(),
                    )
                )
                next_heartbeat += max(0.2, args.heartbeat_interval)

            did_work = False
            for sensor_type in SENSOR_DEFINITIONS:
                rate = max(0.01, rates.get(sensor_type, 1.0))
                # Catch up if the process was briefly delayed, but cap each pass
                # so a long pause cannot monopolise the loop.
                emitted_this_pass = 0
                while elapsed + 1e-9 >= next_due[sensor_type] and emitted_this_pass < 5:
                    did_work = True
                    emitted_this_pass += 1
                    sequence = sequences[sensor_type]
                    sequences[sensor_type] += 1
                    next_due[sensor_type] += 1.0 / rate

                    if sensor_type == "GNSS" and in_gnss_dropout(elapsed, faults):
                        fault_dropped[sensor_type] += 1
                        continue

                    message = build_raw_message(
                        args.vehicle_id,
                        mission_id,
                        sensor_type,
                        sequence,
                        elapsed,
                        wall_start,
                        scenario,
                        rng,
                        args.vehicle_type,
                        effective_parameters,
                    )
                    publisher.submit_raw(message)
                    generated[sensor_type] += 1

                    duplicate_every = int(faults.get("duplicate_every_n", 0) or 0)
                    if (
                        duplicate_every > 0
                        and sequence > 0
                        and sequence % duplicate_every == 0
                    ):
                        publisher.submit_raw(message)

            if not did_work:
                next_sensor_due = min(next_due.values())
                next_wakeup = min(next_sensor_due, next_heartbeat)
                sleep_s = max(0.001, min(0.02, next_wakeup - elapsed))
                time.sleep(sleep_s)
    except Exception as exc:
        fatal_error = exc
        stop_requested = True
        print(f"Simulator failed: {exc}", file=sys.stderr)
    finally:
        publisher.submit_heartbeat(
            build_heartbeat(
                args.vehicle_id,
                mission_id,
                "STOPPING",
                publisher.pending_count(),
            )
        )
        publisher.close(drain_timeout_s=args.drain_timeout)

    target = "abort" if stop_requested or fatal_error is not None else "complete"
    status, detail = transition_mission_with_retry(api_base, mission_id, target)
    if status not in {200, 409}:
        print(
            f"Warning: mission transition failed ({status}): {detail}", file=sys.stderr
        )

    print("Simulation summary:")
    for sensor_type in SENSOR_DEFINITIONS:
        print(
            f"  {sensor_type:<15} generated={generated[sensor_type]:5d} "
            f"scenario_dropped={fault_dropped[sensor_type]:5d}"
        )
    print("  Publisher")
    for key in (
        "submitted",
        "sent",
        "failed_attempts",
        "retried",
        "duplicate_accepted",
        "dropped",
        "queue_peak",
    ):
        print(f"    {key:<20} {publisher.stats[key]}")
    print(f"Mission state requested: {target.upper()}")
    return 1 if stop_requested or fatal_error is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
