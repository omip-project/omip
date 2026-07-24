from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..schemas import ScenarioCreate
from .base import RepositoryBase


class ScenarioRepository(RepositoryBase):
    """Persistence operations for scenario templates.

    Business orchestration, item applicability, file export and mission snapshot
    construction remain in ``EnvironmentContextService``.
    """

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    coordinate_frame TEXT NOT NULL DEFAULT 'LOCAL_ENU',
                    origin_json TEXT NOT NULL DEFAULT '{}',
                    default_duration_s REAL NOT NULL DEFAULT 60.0,
                    motion_json TEXT NOT NULL DEFAULT '{}',
                    obstacle_avoidance_json TEXT NOT NULL DEFAULT '{}',
                    sensor_rates_hz_json TEXT NOT NULL DEFAULT '{}',
                    quality_json TEXT NOT NULL DEFAULT '{}',
                    faults_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(scenarios)").fetchall()
            }
            if "obstacle_avoidance_json" not in columns:
                connection.execute(
                    "ALTER TABLE scenarios ADD COLUMN obstacle_avoidance_json "
                    "TEXT NOT NULL DEFAULT '{}'"
                )

    def list_rows(self, *, enabled_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM scenarios"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY built_in DESC, name, scenario_id"
        with self._connect() as connection:
            return connection.execute(sql, params).fetchall()

    def get_row(self, scenario_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
            ).fetchone()

    def count_items(self, scenario_id: str) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                   (SELECT COUNT(*) FROM obstacles WHERE scenario_id = ?) AS obstacles,
                   (SELECT COUNT(*) FROM environment_constraints WHERE scenario_id = ?) AS constraints,
                   (SELECT COUNT(*) FROM external_fields WHERE scenario_id = ?) AS fields""",
                (scenario_id, scenario_id, scenario_id),
            ).fetchone()
        return {
            "obstacles": int(row["obstacles"]),
            "constraints": int(row["constraints"]),
            "fields": int(row["fields"]),
        }

    def upsert(
        self,
        request: ScenarioCreate,
        *,
        built_in: bool,
    ) -> None:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT version, created_at_utc FROM scenarios WHERE scenario_id = ?",
                (request.scenario_id,),
            ).fetchone()
            version = int(existing["version"]) + 1 if existing else 1
            created = existing["created_at_utc"] if existing else now
            connection.execute(
                """INSERT INTO scenarios(
                    scenario_id,name,description,coordinate_frame,origin_json,default_duration_s,
                    motion_json,obstacle_avoidance_json,sensor_rates_hz_json,quality_json,faults_json,
                    metadata_json,enabled,built_in,version,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    name=excluded.name,description=excluded.description,
                    coordinate_frame=excluded.coordinate_frame,origin_json=excluded.origin_json,
                    default_duration_s=excluded.default_duration_s,motion_json=excluded.motion_json,
                    obstacle_avoidance_json=excluded.obstacle_avoidance_json,
                    sensor_rates_hz_json=excluded.sensor_rates_hz_json,
                    quality_json=excluded.quality_json,faults_json=excluded.faults_json,
                    metadata_json=excluded.metadata_json,enabled=excluded.enabled,
                    built_in=MAX(scenarios.built_in,excluded.built_in),version=excluded.version,
                    updated_at_utc=excluded.updated_at_utc""",
                (
                    request.scenario_id,
                    request.name,
                    request.description,
                    request.coordinate_frame,
                    json.dumps(request.origin, separators=(",", ":"), default=str),
                    request.default_duration_s,
                    json.dumps(request.motion, separators=(",", ":"), default=str),
                    json.dumps(request.obstacle_avoidance, separators=(",", ":"), default=str),
                    json.dumps(request.sensor_rates_hz, separators=(",", ":"), default=str),
                    json.dumps(request.quality, separators=(",", ":"), default=str),
                    json.dumps(request.faults, separators=(",", ":"), default=str),
                    json.dumps(request.metadata, separators=(",", ":"), default=str),
                    int(request.enabled),
                    int(built_in),
                    version,
                    created,
                    now,
                ),
            )

    def delete_items(self, scenario_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM obstacles WHERE scenario_id = ?", (scenario_id,))
            connection.execute(
                "DELETE FROM environment_constraints WHERE scenario_id = ?", (scenario_id,)
            )
            connection.execute("DELETE FROM external_fields WHERE scenario_id = ?", (scenario_id,))

    def simulation_run_count(self, scenario_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS c FROM simulation_runs WHERE scenario_id = ?",
                (scenario_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def delete(self, scenario_id: str) -> bool:
        with self._lock, self._connect() as connection:
            return (
                connection.execute(
                    "DELETE FROM scenarios WHERE scenario_id = ?", (scenario_id,)
                ).rowcount
                > 0
            )

    def touch(self, scenario_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE scenarios SET version = version + 1, updated_at_utc = ? "
                "WHERE scenario_id = ?",
                (self._utc_now().isoformat(), scenario_id),
            )
