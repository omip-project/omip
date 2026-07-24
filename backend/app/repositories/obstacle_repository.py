from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..schemas import ObstacleCreate
from .base import RepositoryBase


class ObstacleRepository(RepositoryBase):
    """SQLite persistence operations for scenario obstacles.

    Scenario validation, scenario-version updates and JSON file export remain
    responsibilities of ``EnvironmentContextService``.
    """

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS obstacles (
                    obstacle_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    obstacle_type TEXT NOT NULL,
                    geometry_json TEXT NOT NULL,
                    coordinate_frame TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    velocity_json TEXT,
                    heading_deg REAL,
                    valid_from_utc TEXT,
                    valid_to_utc TEXT,
                    applies_to_vehicle_types_json TEXT NOT NULL DEFAULT '[]',
                    applies_to_vehicle_ids_json TEXT NOT NULL DEFAULT '[]',
                    required_capabilities_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY (scenario_id)
                        REFERENCES scenarios(scenario_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_obstacles_scenario
                    ON obstacles(scenario_id);
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), default=str)

    @staticmethod
    def _load(value: str | None, default: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return default

    def create(
        self,
        scenario_id: str,
        item_id: str,
        request: ObstacleCreate,
    ) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO obstacles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    scenario_id,
                    request.name,
                    request.obstacle_type,
                    self._json(request.geometry.model_dump(mode="json")),
                    request.coordinate_frame,
                    request.source,
                    request.confidence,
                    (
                        self._json(request.velocity.model_dump(mode="json"))
                        if request.velocity
                        else None
                    ),
                    request.heading_deg,
                    str(request.valid_from_utc) if request.valid_from_utc else None,
                    str(request.valid_to_utc) if request.valid_to_utc else None,
                    self._json(request.applies_to_vehicle_types),
                    self._json(request.applies_to_vehicle_ids),
                    self._json(request.required_capabilities),
                    self._json(request.metadata),
                    now,
                    now,
                ),
            )
        return self.get(item_id) or {}

    def list_for_scenario(self, scenario_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM obstacles "
                "WHERE scenario_id = ? ORDER BY name, obstacle_id",
                (scenario_id,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM obstacles WHERE obstacle_id = ?",
                (item_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def delete(self, item_id: str) -> bool:
        with self._lock, self._connect() as connection:
            return (
                connection.execute(
                    "DELETE FROM obstacles WHERE obstacle_id = ?",
                    (item_id,),
                ).rowcount
                > 0
            )

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for source, target, default in (
            ("geometry_json", "geometry", {}),
            ("velocity_json", "velocity", None),
            ("applies_to_vehicle_types_json", "applies_to_vehicle_types", []),
            ("applies_to_vehicle_ids_json", "applies_to_vehicle_ids", []),
            ("required_capabilities_json", "required_capabilities", []),
            ("metadata_json", "metadata", {}),
        ):
            item[target] = self._load(item.pop(source), default)
        return item
