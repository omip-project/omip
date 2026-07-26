from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..schemas import EnvironmentConstraintCreate
from .base import RepositoryBase


class ConstraintRepository(RepositoryBase):
    """SQLite persistence operations for environment constraints.

    Scenario validation, scenario-version updates and scenario-file export remain
    responsibilities of ``EnvironmentContextService``.
    """

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS environment_constraints (
                    constraint_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    constraint_type TEXT NOT NULL,
                    geometry_json TEXT,
                    value_json TEXT,
                    unit TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    applies_to_vehicle_types_json TEXT NOT NULL DEFAULT '[]',
                    applies_to_vehicle_ids_json TEXT NOT NULL DEFAULT '[]',
                    required_capabilities_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY (scenario_id)
                        REFERENCES scenarios(scenario_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_constraints_scenario
                    ON environment_constraints(scenario_id);
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
        request: EnvironmentConstraintCreate,
    ) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO environment_constraints
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    scenario_id,
                    request.name,
                    request.constraint_type,
                    (
                        self._json(request.geometry.model_dump(mode="json"))
                        if request.geometry
                        else None
                    ),
                    self._json(request.value),
                    request.unit,
                    request.severity,
                    int(request.enabled),
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
                "SELECT * FROM environment_constraints "
                "WHERE scenario_id = ? ORDER BY name, constraint_id",
                (scenario_id,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM environment_constraints "
                "WHERE constraint_id = ?",
                (item_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def delete(self, item_id: str) -> bool:
        with self._lock, self._connect() as connection:
            return (
                connection.execute(
                    "DELETE FROM environment_constraints "
                    "WHERE constraint_id = ?",
                    (item_id,),
                ).rowcount
                > 0
            )

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        for source, target, default in (
            ("geometry_json", "geometry", None),
            ("value_json", "value", None),
            ("applies_to_vehicle_types_json", "applies_to_vehicle_types", []),
            ("applies_to_vehicle_ids_json", "applies_to_vehicle_ids", []),
            ("required_capabilities_json", "required_capabilities", []),
            ("metadata_json", "metadata", {}),
        ):
            item[target] = self._load(item.pop(source), default)
        return item
