from __future__ import annotations

import json
from typing import Any

from .base import RepositoryBase


class MissionEnvironmentSnapshotRepository(RepositoryBase):
    """SQLite persistence for immutable mission environment snapshots.

    Snapshot construction, applicability filtering and SHA-256 generation remain
    responsibilities of ``EnvironmentContextService``.
    """

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS mission_environment_snapshots (
                    mission_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    scenario_version INTEGER NOT NULL,
                    vehicle_id TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY (mission_id)
                        REFERENCES missions(mission_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_environment_snapshot_scenario
                    ON mission_environment_snapshots(scenario_id);
                """
            )

    def save(
        self,
        *,
        mission_id: str,
        scenario_id: str,
        scenario_version: int,
        vehicle_id: str,
        vehicle_type: str,
        snapshot_json: str,
        sha256: str,
        created_at_utc: str,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO mission_environment_snapshots(
                    mission_id,
                    scenario_id,
                    scenario_version,
                    vehicle_id,
                    vehicle_type,
                    snapshot_json,
                    sha256,
                    created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    mission_id,
                    scenario_id,
                    int(scenario_version),
                    vehicle_id,
                    vehicle_type,
                    snapshot_json,
                    sha256,
                    created_at_utc,
                ),
            )

    def get_by_mission_id(self, mission_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mission_environment_snapshots "
                "WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            snapshot = json.loads(row["snapshot_json"])
        except (TypeError, json.JSONDecodeError):
            snapshot = {}

        snapshot["sha256"] = row["sha256"]
        snapshot["scenario_version"] = row["scenario_version"]
        snapshot["created_at_utc"] = row["created_at_utc"]
        return snapshot
