from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..schemas import VehicleProfileCreate, VehicleProfileUpdate
from .base import RepositoryBase


class VehicleProfileRepository(RepositoryBase):
    """Persistence operations for vehicle profiles and parameter definitions."""

    @staticmethod
    def _decode_vehicle_profile(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["capabilities"] = json.loads(record.pop("capabilities_json") or "{}")
        record["parameters"] = json.loads(record.pop("parameters_json") or "{}")
        record["enabled"] = bool(record["enabled"])
        record["built_in"] = bool(record["built_in"])
        return record

    def seed_vehicle_parameter_definitions(
        self, definitions: dict[str, dict[str, dict[str, Any]]]
    ) -> None:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            for vehicle_type, items in definitions.items():
                for path, definition in items.items():
                    connection.execute(
                        """
                        INSERT INTO vehicle_parameter_definitions (
                            vehicle_type, parameter_path, definition_json, updated_at_utc
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(vehicle_type, parameter_path) DO UPDATE SET
                            definition_json = excluded.definition_json,
                            updated_at_utc = excluded.updated_at_utc
                        """,
                        (
                            vehicle_type,
                            path,
                            json.dumps(definition, separators=(",", ":")),
                            now,
                        ),
                    )

    def list_vehicle_parameter_definitions(
        self, vehicle_type: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM vehicle_parameter_definitions"
        params: list[Any] = []
        if vehicle_type:
            sql += " WHERE vehicle_type = ?"
            params.append(vehicle_type)
        sql += " ORDER BY vehicle_type, parameter_path"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["definition"] = json.loads(record.pop("definition_json") or "{}")
            result.append(record)
        return result

    def upsert_vehicle_profile(
        self, request: VehicleProfileCreate, *, built_in: bool = False
    ) -> dict[str, Any]:
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicle_profiles (
                    profile_id, profile_name, vehicle_type, schema_version, description,
                    capabilities_json, parameters_json, enabled, built_in,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    profile_name = excluded.profile_name,
                    vehicle_type = excluded.vehicle_type,
                    schema_version = excluded.schema_version,
                    description = excluded.description,
                    capabilities_json = excluded.capabilities_json,
                    parameters_json = excluded.parameters_json,
                    enabled = excluded.enabled,
                    built_in = MAX(vehicle_profiles.built_in, excluded.built_in),
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    request.profile_id,
                    request.profile_name,
                    request.vehicle_type,
                    request.schema_version,
                    request.description,
                    json.dumps(request.capabilities, separators=(",", ":")),
                    json.dumps(request.parameters, separators=(",", ":")),
                    1 if request.enabled else 0,
                    1 if built_in else 0,
                    now,
                    now,
                ),
            )
        profile = self.get_vehicle_profile(request.profile_id)
        if profile is None:
            raise RuntimeError("Vehicle profile was not created")
        return profile

    def get_vehicle_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vehicle_profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
        return self._decode_vehicle_profile(row) if row else None

    def list_vehicle_profiles(
        self, vehicle_type: str | None = None, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if vehicle_type:
            clauses.append("vehicle_type = ?")
            params.append(vehicle_type)
        if enabled_only:
            clauses.append("enabled = 1")
        sql = "SELECT * FROM vehicle_profiles"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY vehicle_type, profile_name"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._decode_vehicle_profile(row) for row in rows]

    def update_vehicle_profile(
        self, profile_id: str, request: VehicleProfileUpdate
    ) -> dict[str, Any] | None:
        current = self.get_vehicle_profile(profile_id)
        if current is None:
            return None
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return current
        mapping = {
            "profile_name": "profile_name",
            "schema_version": "schema_version",
            "description": "description",
            "capabilities": "capabilities_json",
            "parameters": "parameters_json",
            "enabled": "enabled",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{mapping[key]} = ?")
            if key in {"capabilities", "parameters"}:
                value = json.dumps(value, separators=(",", ":"))
            elif key == "enabled":
                value = 1 if value else 0
            params.append(value)
        assignments.append("updated_at_utc = ?")
        params.extend([self._utc_now().isoformat(), profile_id])
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE vehicle_profiles SET {', '.join(assignments)} WHERE profile_id = ?",
                params,
            )
        return self.get_vehicle_profile(profile_id)

    def delete_vehicle_profile(self, profile_id: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT built_in FROM vehicle_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            if not row:
                return False
            if bool(row["built_in"]):
                raise ValueError(
                    "Built-in profiles cannot be deleted; disable or copy the profile instead"
                )
            in_use = connection.execute(
                "SELECT COUNT(*) AS total FROM simulation_runs WHERE vehicle_profile_id = ?",
                (profile_id,),
            ).fetchone()
            if in_use and int(in_use["total"]) > 0:
                raise ValueError("Vehicle profile is referenced by simulation runs")
            return (
                connection.execute(
                    "DELETE FROM vehicle_profiles WHERE profile_id = ?", (profile_id,)
                ).rowcount
                > 0
            )
