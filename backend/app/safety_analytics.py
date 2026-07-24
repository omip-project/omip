from __future__ import annotations

import json
import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class SafetyAnalyticsService:
    """Constraint-violation and near-miss analytics for normalised telemetry."""

    def __init__(
        self, repository: Any, environment_context: Any, obstacle_service: Any
    ) -> None:
        self.repository = repository
        self.environment_context = environment_context
        self.obstacle_service = obstacle_service
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
    def _json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), default=str)

    @staticmethod
    def _load(value: str | None, default: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return default

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS constraint_violations (
                    violation_id TEXT PRIMARY KEY,
                    active_key TEXT,
                    mission_id TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    constraint_id TEXT NOT NULL,
                    violation_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_timestamp_utc TEXT NOT NULL,
                    end_timestamp_utc TEXT,
                    duration_s REAL,
                    sample_count INTEGER NOT NULL DEFAULT 1,
                    measured_value REAL,
                    limit_value REAL,
                    maximum_exceedance REAL,
                    unit TEXT,
                    position_json TEXT NOT NULL DEFAULT '{}',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_constraint_violations_active
                    ON constraint_violations(active_key) WHERE active_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_constraint_violations_mission_time
                    ON constraint_violations(mission_id, start_timestamp_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_constraint_violations_type_status
                    ON constraint_violations(violation_type, status);

                CREATE TABLE IF NOT EXISTS near_miss_events (
                    near_miss_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    obstacle_id TEXT NOT NULL,
                    interaction_id TEXT,
                    timestamp_utc TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    clearance_m REAL NOT NULL,
                    time_to_collision_s REAL,
                    closing_speed_mps REAL,
                    position_json TEXT NOT NULL DEFAULT '{}',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_near_miss_interaction
                    ON near_miss_events(interaction_id) WHERE interaction_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_near_miss_mission_time
                    ON near_miss_events(mission_id, timestamp_utc DESC);
                """)

    @staticmethod
    def _point_in_polygon(x: float, y: float, points: list[dict[str, Any]]) -> bool:
        if len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i, point in enumerate(points):
            xi = float(point.get("x_m", 0.0))
            yi = float(point.get("y_m", 0.0))
            xj = float(points[j].get("x_m", 0.0))
            yj = float(points[j].get("y_m", 0.0))
            if (yi > y) != (yj > y):
                crossing_x = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
                if x < crossing_x:
                    inside = not inside
            j = i
        return inside

    @classmethod
    def _inside_geometry(
        cls, position: dict[str, float], geometry: dict[str, Any]
    ) -> bool:
        x, y, z = position["x_m"], position["y_m"], position["z_m"]
        kind = str(geometry.get("geometry_type", "")).upper()
        centre = geometry.get("position") or {}
        cx = float(centre.get("x_m", 0.0))
        cy = float(centre.get("y_m", 0.0))
        cz = float(centre.get("z_m", 0.0))
        if kind == "CIRCLE":
            return math.hypot(x - cx, y - cy) <= float(geometry.get("radius_m", 0.0))
        if kind == "SPHERE":
            return math.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) <= float(
                geometry.get("radius_m", 0.0)
            )
        if kind == "BOX":
            return (
                abs(x - cx) <= float(geometry.get("length_m", 0.0)) / 2
                and abs(y - cy) <= float(geometry.get("width_m", 0.0)) / 2
                and abs(z - cz) <= max(0.1, float(geometry.get("height_m", 0.0)) / 2)
            )
        if kind == "POLYGON":
            return cls._point_in_polygon(x, y, geometry.get("points") or [])
        return True  # global constraint

    @staticmethod
    def _classification(
        clearance: float, ttc: float | None, safety_radius: float
    ) -> tuple[str, str]:
        near = max(0.75, safety_radius * 0.75)
        caution = max(1.5, safety_radius * 1.5)
        if clearance <= 0:
            return "COLLISION", "CRITICAL"
        if clearance < near and (ttc is None or ttc < 2.0):
            return "CRITICAL_NEAR_MISS", "CRITICAL"
        if clearance < caution or (ttc is not None and ttc < 4.0):
            return "NEAR_MISS", "WARNING"
        return "SAFE", "INFO"

    def _upsert_violation(
        self,
        telemetry: dict[str, Any],
        constraint: dict[str, Any],
        violation_type: str,
        severity: str,
        measured: float | None,
        limit: float | None,
        unit: str | None,
        position: dict[str, float],
        details: dict[str, Any],
    ) -> dict[str, Any]:
        mission_id = str(telemetry["mission_id"])
        vehicle_id = str(telemetry["vehicle_id"])
        constraint_id = str(constraint.get("constraint_id", violation_type))
        active_key = f"{mission_id}|{vehicle_id}|{constraint_id}|{violation_type}"
        timestamp = str(telemetry["timestamp_utc"])
        exceedance = (
            abs(measured - limit)
            if measured is not None and limit is not None
            else None
        )
        now = self._now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM constraint_violations WHERE active_key=?", (active_key,)
            ).fetchone()
            if row:
                start = datetime.fromisoformat(
                    str(row["start_timestamp_utc"]).replace("Z", "+00:00")
                )
                current = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                duration = max(0.0, (current - start).total_seconds())
                maximum = max(
                    float(row["maximum_exceedance"] or 0.0), float(exceedance or 0.0)
                )
                connection.execute(
                    """UPDATE constraint_violations SET status='ONGOING', end_timestamp_utc=?,
                    duration_s=?, sample_count=sample_count+1, measured_value=?, limit_value=?,
                    maximum_exceedance=?, position_json=?, details_json=?, updated_at_utc=?
                    WHERE violation_id=?""",
                    (
                        timestamp,
                        duration,
                        measured,
                        limit,
                        maximum,
                        self._json(position),
                        self._json(details),
                        now,
                        row["violation_id"],
                    ),
                )
                violation_id = str(row["violation_id"])
            else:
                violation_id = f"VIOLATION-{uuid4().hex[:12].upper()}"
                connection.execute(
                    """INSERT INTO constraint_violations(
                    violation_id,active_key,mission_id,vehicle_id,constraint_id,violation_type,
                    severity,status,start_timestamp_utc,end_timestamp_utc,duration_s,sample_count,
                    measured_value,limit_value,maximum_exceedance,unit,position_json,details_json,
                    created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        violation_id,
                        active_key,
                        mission_id,
                        vehicle_id,
                        constraint_id,
                        violation_type,
                        severity,
                        "OPEN",
                        timestamp,
                        timestamp,
                        0.0,
                        1,
                        measured,
                        limit,
                        exceedance,
                        unit,
                        self._json(position),
                        self._json(details),
                        now,
                        now,
                    ),
                )
            result = connection.execute(
                "SELECT * FROM constraint_violations WHERE violation_id=?",
                (violation_id,),
            ).fetchone()
        return self._decode_violation(result)

    def _resolve_inactive(
        self, mission_id: str, vehicle_id: str, active_keys: set[str], timestamp: str
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM constraint_violations
                WHERE mission_id=? AND vehicle_id=? AND active_key IS NOT NULL
                AND status IN ('OPEN','ONGOING')""",
                (mission_id, vehicle_id),
            ).fetchall()
            for row in rows:
                if str(row["active_key"]) in active_keys:
                    continue
                start = datetime.fromisoformat(
                    str(row["start_timestamp_utc"]).replace("Z", "+00:00")
                )
                end = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                connection.execute(
                    """UPDATE constraint_violations SET status='RESOLVED', active_key=NULL,
                    end_timestamp_utc=?, duration_s=?, updated_at_utc=? WHERE violation_id=?""",
                    (
                        timestamp,
                        max(0.0, (end - start).total_seconds()),
                        self._now(),
                        row["violation_id"],
                    ),
                )
                updated = connection.execute(
                    "SELECT * FROM constraint_violations WHERE violation_id=?",
                    (row["violation_id"],),
                ).fetchone()
                resolved.append(self._decode_violation(updated))
        return resolved

    def analyse(
        self, telemetry: dict[str, Any], interaction: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        mission_id = str(telemetry.get("mission_id", ""))
        vehicle_id = str(telemetry.get("vehicle_id", ""))
        snapshot = self.environment_context.get_mission_environment(mission_id)
        if not snapshot:
            return {"violations": [], "resolved": [], "near_miss": None}

        position_data = telemetry.get("position") or {}
        position = {
            "x_m": float(position_data.get("x_m", 0.0)),
            "y_m": float(position_data.get("y_m", 0.0)),
            "z_m": float(position_data.get("z_m", 0.0)),
        }
        speed = float((telemetry.get("velocity") or {}).get("speed_mps", 0.0))
        battery = float((telemetry.get("state") or {}).get("battery_percent", 100.0))
        violations: list[dict[str, Any]] = []
        active_keys: set[str] = set()

        for constraint in snapshot.get("constraints") or []:
            ctype = str(constraint.get("constraint_type", "")).upper()
            geometry = constraint.get("geometry") or {}
            inside = self._inside_geometry(position, geometry)
            value = constraint.get("value")
            limit = float(value) if value is not None else None
            violation_type = None
            measured = None
            violated = False

            if ctype == "SPEED_LIMIT" and inside and limit is not None:
                measured, violated, violation_type = (
                    speed,
                    speed > limit,
                    "SPEED_LIMIT_VIOLATION",
                )
            elif ctype == "NO_ENTRY_ZONE":
                measured, violated, violation_type = (
                    1.0 if inside else 0.0,
                    inside,
                    "NO_ENTRY_ZONE_VIOLATION",
                )
                limit = 0.0
            elif ctype == "MAXIMUM_ALTITUDE" and limit is not None:
                measured, violated, violation_type = (
                    position["z_m"],
                    position["z_m"] > limit,
                    "ALTITUDE_LIMIT_VIOLATION",
                )
            elif ctype == "MINIMUM_ALTITUDE" and limit is not None:
                measured, violated, violation_type = (
                    position["z_m"],
                    position["z_m"] < limit,
                    "ALTITUDE_LIMIT_VIOLATION",
                )
            elif ctype == "MAXIMUM_DEPTH" and limit is not None:
                measured = max(0.0, -position["z_m"])
                violated, violation_type = measured > limit, "DEPTH_LIMIT_VIOLATION"
            elif ctype == "MINIMUM_DEPTH" and limit is not None:
                measured = max(0.0, -position["z_m"])
                violated, violation_type = measured < limit, "DEPTH_LIMIT_VIOLATION"
            elif ctype == "MISSION_BOUNDARY":
                measured, violated, violation_type = (
                    1.0 if inside else 0.0,
                    not inside,
                    "MISSION_BOUNDARY_EXIT",
                )
                limit = 1.0
            elif ctype == "REQUIRED_CORRIDOR":
                measured, violated, violation_type = (
                    1.0 if inside else 0.0,
                    not inside,
                    "REQUIRED_CORRIDOR_EXIT",
                )
                limit = 1.0
            elif ctype == "BATTERY_RETURN_THRESHOLD" and limit is not None:
                measured, violated, violation_type = (
                    battery,
                    battery < limit,
                    "LOW_BATTERY_RETURN_VIOLATION",
                )

            if not violated or violation_type is None:
                continue
            severity = (
                "CRITICAL"
                if ctype in {"NO_ENTRY_ZONE", "MISSION_BOUNDARY"}
                else "WARNING"
            )
            key = f"{mission_id}|{vehicle_id}|{constraint.get('constraint_id', violation_type)}|{violation_type}"
            active_keys.add(key)
            violations.append(
                self._upsert_violation(
                    telemetry,
                    constraint,
                    violation_type,
                    severity,
                    measured,
                    limit,
                    constraint.get("unit"),
                    position,
                    {
                        "constraint_name": constraint.get("name"),
                        "constraint_type": ctype,
                    },
                )
            )

        resolved = self._resolve_inactive(
            mission_id, vehicle_id, active_keys, str(telemetry["timestamp_utc"])
        )
        near_miss = (
            self._record_near_miss(telemetry, interaction, position)
            if interaction
            else None
        )
        return {"violations": violations, "resolved": resolved, "near_miss": near_miss}

    def _record_near_miss(
        self,
        telemetry: dict[str, Any],
        interaction: dict[str, Any],
        position: dict[str, float],
    ) -> dict[str, Any] | None:
        classification, severity = self._classification(
            float(interaction.get("clearance_m", 9999.0)),
            interaction.get("time_to_collision_s"),
            float(interaction.get("safety_radius_m", 1.0)),
        )
        if classification == "SAFE":
            return None
        record = {
            "near_miss_id": f"NEARMISS-{uuid4().hex[:12].upper()}",
            "mission_id": str(telemetry["mission_id"]),
            "vehicle_id": str(telemetry["vehicle_id"]),
            "obstacle_id": str(interaction.get("obstacle_id", "UNKNOWN")),
            "interaction_id": interaction.get("interaction_id"),
            "timestamp_utc": str(telemetry["timestamp_utc"]),
            "classification": classification,
            "severity": severity,
            "clearance_m": float(interaction.get("clearance_m", 0.0)),
            "time_to_collision_s": interaction.get("time_to_collision_s"),
            "closing_speed_mps": interaction.get("closing_speed_mps"),
            "position": position,
            "details": {"risk_level": interaction.get("risk_level")},
        }
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO near_miss_events(
                near_miss_id,mission_id,vehicle_id,obstacle_id,interaction_id,timestamp_utc,
                classification,severity,clearance_m,time_to_collision_s,closing_speed_mps,
                position_json,details_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record["near_miss_id"],
                    record["mission_id"],
                    record["vehicle_id"],
                    record["obstacle_id"],
                    record["interaction_id"],
                    record["timestamp_utc"],
                    record["classification"],
                    record["severity"],
                    record["clearance_m"],
                    record["time_to_collision_s"],
                    record["closing_speed_mps"],
                    self._json(position),
                    self._json(record["details"]),
                ),
            )
            row = connection.execute(
                "SELECT * FROM near_miss_events WHERE interaction_id=?",
                (record["interaction_id"],),
            ).fetchone()
        return self._decode_near_miss(row) if row else record

    @classmethod
    def _decode_violation(cls, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["position"] = cls._load(item.pop("position_json", "{}"), {})
        item["details"] = cls._load(item.pop("details_json", "{}"), {})
        return item

    @classmethod
    def _decode_near_miss(cls, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["position"] = cls._load(item.pop("position_json", "{}"), {})
        item["details"] = cls._load(item.pop("details_json", "{}"), {})
        return item

    def list_violations(
        self,
        mission_id: str,
        violation_type: str | None = None,
        status: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM constraint_violations WHERE mission_id=?"
        params: list[Any] = [mission_id]
        if violation_type:
            sql += " AND violation_type=?"
            params.append(violation_type)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY start_timestamp_utc DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            return [
                self._decode_violation(row)
                for row in connection.execute(sql, params).fetchall()
            ]

    def list_near_misses(
        self, mission_id: str, classification: str | None = None, limit: int = 5000
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM near_miss_events WHERE mission_id=?"
        params: list[Any] = [mission_id]
        if classification:
            sql += " AND classification=?"
            params.append(classification)
        sql += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            return [
                self._decode_near_miss(row)
                for row in connection.execute(sql, params).fetchall()
            ]

    def constraint_summary(self, mission_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT violation_type,status,COUNT(*) AS count FROM constraint_violations WHERE mission_id=? GROUP BY violation_type,status",
                (mission_id,),
            ).fetchall()
        return {
            "mission_id": mission_id,
            "total": sum(int(r["count"]) for r in rows),
            "by_type_and_status": [dict(r) for r in rows],
        }

    def safety_summary(self, mission_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            near = connection.execute(
                """SELECT COUNT(*) total, MIN(clearance_m) min_clearance,
                MIN(time_to_collision_s) min_ttc,
                SUM(CASE WHEN classification='NEAR_MISS' THEN 1 ELSE 0 END) near_miss_count,
                SUM(CASE WHEN classification='CRITICAL_NEAR_MISS' THEN 1 ELSE 0 END) critical_count,
                SUM(CASE WHEN classification='COLLISION' THEN 1 ELSE 0 END) collision_count
                FROM near_miss_events WHERE mission_id=?""",
                (mission_id,),
            ).fetchone()
            violations = connection.execute(
                "SELECT COUNT(*) total, SUM(CASE WHEN status IN ('OPEN','ONGOING') THEN 1 ELSE 0 END) active FROM constraint_violations WHERE mission_id=?",
                (mission_id,),
            ).fetchone()
        return {
            "mission_id": mission_id,
            "near_miss_samples": int(near["total"] or 0),
            "minimum_clearance_m": near["min_clearance"],
            "minimum_time_to_collision_s": near["min_ttc"],
            "near_miss_count": int(near["near_miss_count"] or 0),
            "critical_near_miss_count": int(near["critical_count"] or 0),
            "collision_count": int(near["collision_count"] or 0),
            "constraint_violation_count": int(violations["total"] or 0),
            "active_constraint_violations": int(violations["active"] or 0),
        }

    def vehicle_constraint_status(self, vehicle_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM constraint_violations WHERE vehicle_id=?
                AND status IN ('OPEN','ONGOING') ORDER BY updated_at_utc DESC""",
                (vehicle_id,),
            ).fetchall()
        return {
            "vehicle_id": vehicle_id,
            "active_violations": [self._decode_violation(r) for r in rows],
        }
