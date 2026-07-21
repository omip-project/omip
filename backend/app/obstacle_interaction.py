from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .schemas import MissionEventCreate


RISK_ORDER = {"CLEAR": 0, "CAUTION": 1, "WARNING": 2, "CRITICAL": 3, "COLLISION": 4}


@dataclass(frozen=True)
class GeometryAssessment:
    centre_distance_m: float
    surface_distance_m: float
    direction_to_obstacle: tuple[float, float, float]
    obstacle_position: tuple[float, float, float]
    obstacle_radius_m: float


class ObstacleInteractionService:
    """Evaluate vehicle safety envelopes against Mission obstacle snapshots.

    The service deliberately uses conservative geometric approximations. It is
    intended for operational monitoring and repeatable simulation experiments,
    not as a certified collision-avoidance controller.
    """

    def __init__(self, repository: Any, environment_context: Any) -> None:
        self.repository = repository
        self.environment_context = environment_context
        self.database_path = Path(repository._database_path)
        self._lock = threading.RLock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _load(value: str | None, default: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return default

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), default=str)

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS obstacle_interactions (
                    interaction_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    obstacle_id TEXT NOT NULL,
                    telemetry_message_id TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    detected_at_utc TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    centre_distance_m REAL NOT NULL,
                    clearance_m REAL NOT NULL,
                    time_to_collision_s REAL,
                    closing_speed_mps REAL NOT NULL,
                    safety_radius_m REAL NOT NULL,
                    obstacle_radius_m REAL NOT NULL,
                    avoidance_active INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(telemetry_message_id, obstacle_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS obstacle_interaction_state (
                    mission_id TEXT NOT NULL,
                    obstacle_id TEXT NOT NULL,
                    last_risk_level TEXT NOT NULL,
                    avoidance_active INTEGER NOT NULL DEFAULT 0,
                    last_interaction_id TEXT,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (mission_id, obstacle_id),
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_obstacle_interactions_mission_time
                    ON obstacle_interactions(mission_id, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_obstacle_interactions_vehicle_time
                    ON obstacle_interactions(vehicle_id, timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_obstacle_interactions_risk
                    ON obstacle_interactions(risk_level, timestamp_utc DESC);
                """
            )

    # ------------------------------------------------------------------
    # Geometry and vehicle safety envelope
    # ------------------------------------------------------------------
    @staticmethod
    def safety_radius(snapshot: dict[str, Any]) -> float:
        params = snapshot.get("effective_vehicle_parameters") or {}
        geometry = params.get("geometry") or {}
        operational = params.get("operational_limits") or {}
        length = max(0.0, float(geometry.get("length_m", 0.0) or 0.0))
        width = max(0.0, float(geometry.get("width_m", 0.0) or 0.0))
        height = max(0.0, float(geometry.get("height_m", 0.0) or 0.0))
        margin = max(
            0.1,
            float(
                operational.get(
                    "safety_margin_m",
                    geometry.get("safety_margin_m", 0.5),
                )
                or 0.5
            ),
        )
        horizontal = 0.5 * math.hypot(length, width)
        if horizontal <= 0.0:
            horizontal = float(operational.get("effective_safety_radius_m", 0.75) or 0.75)
        vehicle_type = str(snapshot.get("vehicle_type", "GROUND_VEHICLE"))
        if vehicle_type in {"UAV", "AUV"}:
            body = max(horizontal, height * 0.5)
        else:
            body = horizontal
        return max(0.25, body + margin)

    @staticmethod
    def _point(geometry: dict[str, Any]) -> tuple[float, float, float]:
        position = geometry.get("position") or {}
        return (
            float(position.get("x_m", 0.0) or 0.0),
            float(position.get("y_m", 0.0) or 0.0),
            float(position.get("z_m", 0.0) or 0.0),
        )

    @staticmethod
    def _dynamic_position(obstacle: dict[str, Any], timestamp: datetime, snapshot: dict[str, Any]) -> tuple[float, float, float]:
        base = ObstacleInteractionService._point(obstacle.get("geometry") or {})
        velocity = obstacle.get("velocity") or {}
        try:
            origin = datetime.fromisoformat(str(snapshot.get("snapshot_created_at_utc")).replace("Z", "+00:00"))
            elapsed = max(0.0, (timestamp - origin).total_seconds())
        except Exception:
            elapsed = 0.0
        return (
            base[0] + float(velocity.get("x", 0.0) or 0.0) * elapsed,
            base[1] + float(velocity.get("y", 0.0) or 0.0) * elapsed,
            base[2] + float(velocity.get("z", 0.0) or 0.0) * elapsed,
        )

    @staticmethod
    def _unit(dx: float, dy: float, dz: float) -> tuple[float, float, float]:
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        if norm <= 1e-12:
            return (1.0, 0.0, 0.0)
        return (dx / norm, dy / norm, dz / norm)

    @staticmethod
    def _point_in_polygon(x: float, y: float, points: list[dict[str, Any]]) -> bool:
        inside = False
        if len(points) < 3:
            return False
        j = len(points) - 1
        for i, point in enumerate(points):
            xi, yi = float(point.get("x_m", 0.0)), float(point.get("y_m", 0.0))
            xj, yj = float(points[j].get("x_m", 0.0)), float(points[j].get("y_m", 0.0))
            if (yi > y) != (yj > y):
                cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
                if x < cross:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float, float]:
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        t = 0.0 if denom <= 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
        qx, qy = ax + t * dx, ay + t * dy
        return math.hypot(px - qx, py - qy), qx, qy

    def assess_geometry(
        self,
        obstacle: dict[str, Any],
        position: tuple[float, float, float],
        timestamp: datetime,
        snapshot: dict[str, Any],
    ) -> GeometryAssessment:
        geometry = obstacle.get("geometry") or {}
        kind = str(geometry.get("geometry_type", "POINT")).upper()
        ox, oy, oz = self._dynamic_position(obstacle, timestamp, snapshot)
        x, y, z = position
        dx, dy, dz = ox - x, oy - y, oz - z
        centre_distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        direction = self._unit(dx, dy, dz)
        radius = 0.0

        if kind == "CIRCLE":
            radius = float(geometry.get("radius_m", 0.0) or 0.0)
            horizontal = math.hypot(dx, dy)
            surface = horizontal - radius
            direction = self._unit(dx, dy, 0.0)
            centre_distance = horizontal
        elif kind == "SPHERE":
            radius = float(geometry.get("radius_m", 0.0) or 0.0)
            surface = centre_distance - radius
        elif kind == "BOX":
            half_x = float(geometry.get("length_m", 0.0) or 0.0) * 0.5
            half_y = float(geometry.get("width_m", 0.0) or 0.0) * 0.5
            half_z = float(geometry.get("height_m", 0.0) or 0.0) * 0.5
            qx, qy, qz = abs(x - ox) - half_x, abs(y - oy) - half_y, abs(z - oz) - half_z
            outside = math.sqrt(max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2 + max(qz, 0.0) ** 2)
            inside = min(max(qx, qy, qz), 0.0)
            surface = outside + inside
            radius = math.sqrt(half_x * half_x + half_y * half_y + half_z * half_z)
        elif kind == "POLYGON":
            points = geometry.get("points") or []
            best = (float("inf"), ox, oy)
            for index, current in enumerate(points):
                nxt = points[(index + 1) % len(points)]
                candidate = self._point_segment_distance(
                    x,
                    y,
                    float(current.get("x_m", 0.0)),
                    float(current.get("y_m", 0.0)),
                    float(nxt.get("x_m", 0.0)),
                    float(nxt.get("y_m", 0.0)),
                )
                if candidate[0] < best[0]:
                    best = candidate
            surface = -best[0] if self._point_in_polygon(x, y, points) else best[0]
            direction = self._unit(best[1] - x, best[2] - y, 0.0)
            centre_distance = math.hypot(ox - x, oy - y)
            radius = max((math.hypot(float(p.get("x_m", 0.0)) - ox, float(p.get("y_m", 0.0)) - oy) for p in points), default=0.0)
        else:
            surface = centre_distance

        return GeometryAssessment(
            centre_distance_m=centre_distance,
            surface_distance_m=surface,
            direction_to_obstacle=direction,
            obstacle_position=(ox, oy, oz),
            obstacle_radius_m=radius,
        )

    @staticmethod
    def classify_risk(clearance: float, time_to_collision: float | None, safety_radius: float) -> str:
        if clearance <= 0.0:
            return "COLLISION"
        if (time_to_collision is not None and time_to_collision <= 2.0) or clearance <= max(0.5, safety_radius * 0.35):
            return "CRITICAL"
        if (time_to_collision is not None and time_to_collision <= 5.0) or clearance <= max(1.5, safety_radius):
            return "WARNING"
        if (time_to_collision is not None and time_to_collision <= 10.0) or clearance <= max(3.0, safety_radius * 2.5):
            return "CAUTION"
        return "CLEAR"

    # ------------------------------------------------------------------
    # Evaluation, persistence and summaries
    # ------------------------------------------------------------------
    def analyse(self, telemetry: dict[str, Any]) -> dict[str, Any] | None:
        mission_id = str(telemetry.get("mission_id", ""))
        if not mission_id:
            return None
        snapshot = self.environment_context.get_mission_environment(mission_id)
        obstacles = list((snapshot or {}).get("obstacles") or [])
        if not snapshot or not obstacles:
            return None

        position_data = telemetry.get("position") or {}
        velocity_data = telemetry.get("velocity") or {}
        position = (
            float(position_data.get("x_m", 0.0) or 0.0),
            float(position_data.get("y_m", 0.0) or 0.0),
            float(position_data.get("z_m", 0.0) or 0.0),
        )
        velocity = (
            float(velocity_data.get("vx_mps", 0.0) or 0.0),
            float(velocity_data.get("vy_mps", 0.0) or 0.0),
            float(velocity_data.get("vz_mps", 0.0) or 0.0),
        )
        timestamp = datetime.fromisoformat(str(telemetry["timestamp_utc"]).replace("Z", "+00:00"))
        safety_radius = self.safety_radius(snapshot)
        avoidance_active = str((telemetry.get("state") or {}).get("operating_mode", "")) == "OBSTACLE_AVOIDANCE"

        candidates: list[tuple[float, dict[str, Any], GeometryAssessment, float, float | None, str]] = []
        for obstacle in obstacles:
            assessment = self.assess_geometry(obstacle, position, timestamp, snapshot)
            clearance = assessment.surface_distance_m - safety_radius
            obstacle_velocity = obstacle.get("velocity") or {}
            relative_v = (
                velocity[0] - float(obstacle_velocity.get("x", 0.0) or 0.0),
                velocity[1] - float(obstacle_velocity.get("y", 0.0) or 0.0),
                velocity[2] - float(obstacle_velocity.get("z", 0.0) or 0.0),
            )
            direction = assessment.direction_to_obstacle
            closing_speed = relative_v[0] * direction[0] + relative_v[1] * direction[1] + relative_v[2] * direction[2]
            ttc = clearance / closing_speed if clearance > 0.0 and closing_speed > 1e-6 else None
            risk = self.classify_risk(clearance, ttc, safety_radius)
            candidates.append((clearance, obstacle, assessment, closing_speed, ttc, risk))

        candidates.sort(key=lambda item: (item[0], -RISK_ORDER[item[5]]))
        clearance, obstacle, assessment, closing_speed, ttc, risk = candidates[0]
        record = {
            "interaction_id": f"INTERACTION-{uuid4().hex[:12].upper()}",
            "mission_id": mission_id,
            "vehicle_id": str(telemetry.get("vehicle_id", "")),
            "obstacle_id": str(obstacle.get("obstacle_id", obstacle.get("name", "UNKNOWN"))),
            "telemetry_message_id": str(telemetry.get("message_id", "")),
            "timestamp_utc": str(telemetry.get("timestamp_utc")),
            "detected_at_utc": self._now(),
            "risk_level": risk,
            "centre_distance_m": round(assessment.centre_distance_m, 6),
            "clearance_m": round(clearance, 6),
            "time_to_collision_s": round(ttc, 6) if ttc is not None else None,
            "closing_speed_mps": round(closing_speed, 6),
            "safety_radius_m": round(safety_radius, 6),
            "obstacle_radius_m": round(assessment.obstacle_radius_m, 6),
            "avoidance_active": avoidance_active,
            "details": {
                "obstacle_name": obstacle.get("name"),
                "obstacle_type": obstacle.get("obstacle_type"),
                "geometry_type": (obstacle.get("geometry") or {}).get("geometry_type"),
                "vehicle_position": {"x_m": position[0], "y_m": position[1], "z_m": position[2]},
                "obstacle_position": {
                    "x_m": assessment.obstacle_position[0],
                    "y_m": assessment.obstacle_position[1],
                    "z_m": assessment.obstacle_position[2],
                },
                "direction_to_obstacle": {"x": assessment.direction_to_obstacle[0], "y": assessment.direction_to_obstacle[1], "z": assessment.direction_to_obstacle[2]},
            },
        }
        self._persist(record)
        self._update_state_and_event(record)
        return record

    def _persist(self, record: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO obstacle_interactions(
                    interaction_id,mission_id,vehicle_id,obstacle_id,telemetry_message_id,
                    timestamp_utc,detected_at_utc,risk_level,centre_distance_m,clearance_m,
                    time_to_collision_s,closing_speed_mps,safety_radius_m,obstacle_radius_m,
                    avoidance_active,details_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["interaction_id"], record["mission_id"], record["vehicle_id"], record["obstacle_id"],
                    record["telemetry_message_id"], record["timestamp_utc"], record["detected_at_utc"], record["risk_level"],
                    record["centre_distance_m"], record["clearance_m"], record["time_to_collision_s"],
                    record["closing_speed_mps"], record["safety_radius_m"], record["obstacle_radius_m"],
                    int(record["avoidance_active"]), self._json(record["details"]),
                ),
            )

    def _update_state_and_event(self, record: dict[str, Any]) -> None:
        mission_id, obstacle_id = record["mission_id"], record["obstacle_id"]
        with self._lock, self._connect() as connection:
            previous = connection.execute(
                "SELECT * FROM obstacle_interaction_state WHERE mission_id=? AND obstacle_id=?",
                (mission_id, obstacle_id),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO obstacle_interaction_state(mission_id,obstacle_id,last_risk_level,avoidance_active,last_interaction_id,updated_at_utc)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(mission_id,obstacle_id) DO UPDATE SET
                    last_risk_level=excluded.last_risk_level,
                    avoidance_active=excluded.avoidance_active,
                    last_interaction_id=excluded.last_interaction_id,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (mission_id, obstacle_id, record["risk_level"], int(record["avoidance_active"]), record["interaction_id"], self._now()),
            )

        previous_risk = str(previous["last_risk_level"]) if previous else "CLEAR"
        previous_avoidance = bool(previous["avoidance_active"]) if previous else False
        entered_risk = RISK_ORDER[record["risk_level"]] >= RISK_ORDER["WARNING"] and RISK_ORDER.get(previous_risk, 0) < RISK_ORDER["WARNING"]
        entered_avoidance = record["avoidance_active"] and not previous_avoidance
        if not (entered_risk or entered_avoidance):
            return
        event_type = "OBSTACLE_AVOIDANCE" if entered_avoidance else "COLLISION_RISK"
        severity = "CRITICAL" if record["risk_level"] in {"CRITICAL", "COLLISION"} else "WARNING"
        description = (
            f"{event_type.replace('_', ' ').title()} near {record['details'].get('obstacle_name') or obstacle_id}; "
            f"clearance {record['clearance_m']:.2f} m"
        )
        try:
            self.repository.create_event(
                mission_id,
                MissionEventCreate(
                    vehicle_id=record["vehicle_id"],
                    event_type=event_type,
                    start_timestamp_utc=datetime.fromisoformat(record["timestamp_utc"].replace("Z", "+00:00")),
                    severity=severity,
                    source="SYSTEM",
                    description=description,
                    metadata={
                        "obstacle_id": obstacle_id,
                        "risk_level": record["risk_level"],
                        "clearance_m": record["clearance_m"],
                        "time_to_collision_s": record["time_to_collision_s"],
                        "interaction_id": record["interaction_id"],
                    },
                ),
            )
        except Exception:
            # Interaction persistence must never prevent telemetry ingestion.
            return

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["avoidance_active"] = bool(item["avoidance_active"])
        item["details"] = ObstacleInteractionService._load(item.pop("details_json", "{}"), {})
        return item

    def list_interactions(
        self,
        *,
        mission_id: str | None = None,
        vehicle_id: str | None = None,
        risk_level: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if mission_id:
            where.append("mission_id=?"); params.append(mission_id)
        if vehicle_id:
            where.append("vehicle_id=?"); params.append(vehicle_id)
        if risk_level:
            where.append("risk_level=?"); params.append(risk_level)
        sql = "SELECT * FROM obstacle_interactions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100000)))
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._decode(row) for row in rows]

    def latest_vehicle_status(self, vehicle_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM obstacle_interactions WHERE vehicle_id=? ORDER BY timestamp_utc DESC LIMIT 1",
                (vehicle_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def mission_summary(self, mission_id: str) -> dict[str, Any] | None:
        mission = self.repository.get_mission(mission_id)
        if mission is None:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       MIN(clearance_m) AS minimum_clearance_m,
                       MIN(CASE WHEN time_to_collision_s IS NOT NULL THEN time_to_collision_s END) AS minimum_ttc_s,
                       SUM(CASE WHEN avoidance_active=1 THEN 1 ELSE 0 END) AS avoidance_samples,
                       SUM(CASE WHEN risk_level='CAUTION' THEN 1 ELSE 0 END) AS caution_samples,
                       SUM(CASE WHEN risk_level='WARNING' THEN 1 ELSE 0 END) AS warning_samples,
                       SUM(CASE WHEN risk_level='CRITICAL' THEN 1 ELSE 0 END) AS critical_samples,
                       SUM(CASE WHEN risk_level='COLLISION' THEN 1 ELSE 0 END) AS collision_samples
                FROM obstacle_interactions WHERE mission_id=?
                """,
                (mission_id,),
            ).fetchone()
            closest = connection.execute(
                "SELECT * FROM obstacle_interactions WHERE mission_id=? ORDER BY clearance_m ASC, timestamp_utc ASC LIMIT 1",
                (mission_id,),
            ).fetchone()
        summary = dict(row) if row else {}
        return {
            "mission_id": mission_id,
            "vehicle_id": mission.get("vehicle_id"),
            "total_samples": int(summary.get("total") or 0),
            "minimum_clearance_m": summary.get("minimum_clearance_m"),
            "minimum_time_to_collision_s": summary.get("minimum_ttc_s"),
            "avoidance_samples": int(summary.get("avoidance_samples") or 0),
            "risk_counts": {
                "CAUTION": int(summary.get("caution_samples") or 0),
                "WARNING": int(summary.get("warning_samples") or 0),
                "CRITICAL": int(summary.get("critical_samples") or 0),
                "COLLISION": int(summary.get("collision_samples") or 0),
            },
            "closest_interaction": self._decode(closest) if closest else None,
        }
