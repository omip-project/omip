from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .repositories import (
    ConstraintRepository,
    ExternalFieldRepository,
    MissionEnvironmentSnapshotRepository,
    ObstacleRepository,
    ScenarioRepository,
)
from .schemas import (EnvironmentConstraintCreate, EnvironmentConstraintUpdate,
                      ExternalFieldCreate, ExternalFieldUpdate, ObstacleCreate,
                      ObstacleUpdate, ScenarioCreate, ScenarioUpdate)


class EnvironmentContextService:
    """Scenario templates, environment objects and immutable mission snapshots.

    Scenario templates are editable.  A simulation run receives a filtered,
    immutable snapshot so later template edits cannot change historical results.
    """

    def __init__(self, repository: Any, scenarios_dir: Path) -> None:
        self.repository = repository
        self.database_path = Path(repository._database_path)
        self.scenarios_dir = Path(scenarios_dir)
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._scenario_repository = ScenarioRepository(
            connect=self._connect,
            lock=self._lock,
            utc_now=lambda: datetime.now(timezone.utc),
        )
        self._obstacle_repository = ObstacleRepository(
            connect=self._connect,
            lock=self._lock,
            utc_now=lambda: datetime.now(timezone.utc),
        )
        self._constraint_repository = ConstraintRepository(
            connect=self._connect,
            lock=self._lock,
            utc_now=lambda: datetime.now(timezone.utc),
        )
        self._external_field_repository = ExternalFieldRepository(
            connect=self._connect,
            lock=self._lock,
            utc_now=lambda: datetime.now(timezone.utc),
        )
        self._mission_environment_snapshot_repository = (
            MissionEnvironmentSnapshotRepository(
                connect=self._connect,
                lock=self._lock,
                utc_now=lambda: datetime.now(timezone.utc),
            )
        )
        self._scenario_repository.initialise()
        self._obstacle_repository.initialise()
        self._constraint_repository.initialise()
        self._external_field_repository.initialise()
        self._mission_environment_snapshot_repository.initialise()
        self.seed_from_files()

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

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:10].upper()}"

    # ------------------------------------------------------------------
    # Scenario templates
    # ------------------------------------------------------------------
    def seed_from_files(self) -> None:
        for path in sorted(self.scenarios_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            raw.setdefault("scenario_id", path.stem)
            if (
                self.get_scenario(str(raw["scenario_id"]), include_items=False)
                is not None
            ):
                continue
            raw.setdefault("name", path.stem.replace("_", " ").title())
            raw.setdefault("description", "")
            raw.setdefault("coordinate_frame", "LOCAL_ENU")
            raw.setdefault("origin", {})
            raw.setdefault("default_duration_s", 60.0)
            raw.setdefault("motion", {})
            raw.setdefault("obstacle_avoidance", {})
            raw.setdefault("sensor_rates_hz", {})
            raw.setdefault("quality", {})
            raw.setdefault("faults", {})
            raw.setdefault("obstacles", [])
            raw.setdefault("constraints", [])
            raw.setdefault("external_fields", [])
            raw.setdefault("metadata", {})
            raw.setdefault("enabled", True)
            try:
                model = ScenarioCreate.model_validate(raw)
            except Exception:
                continue
            self.upsert_scenario(
                model, built_in=True, replace_items=True, write_file=False
            )

    def list_scenarios(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        rows = self._scenario_repository.list_rows(enabled_only=enabled_only)
        return [self._decode_scenario(row, include_items=False) for row in rows]

    def get_scenario(
        self, scenario_id: str, *, include_items: bool = True
    ) -> dict[str, Any] | None:
        row = self._scenario_repository.get_row(scenario_id)
        if row is None:
            return None
        return self._decode_scenario(row, include_items=include_items)

    def _decode_scenario(
        self, row: sqlite3.Row, *, include_items: bool
    ) -> dict[str, Any]:
        record = dict(row)
        record["origin"] = self._load(record.pop("origin_json"), {})
        record["motion"] = self._load(record.pop("motion_json"), {})
        record["obstacle_avoidance"] = self._load(
            record.pop("obstacle_avoidance_json", "{}"), {}
        )
        record["sensor_rates_hz"] = self._load(record.pop("sensor_rates_hz_json"), {})
        record["quality"] = self._load(record.pop("quality_json"), {})
        record["faults"] = self._load(record.pop("faults_json"), {})
        record["metadata"] = self._load(record.pop("metadata_json"), {})
        record["enabled"] = bool(record["enabled"])
        record["built_in"] = bool(record["built_in"])
        if include_items:
            record["obstacles"] = self.list_obstacles(record["scenario_id"])
            record["constraints"] = self.list_constraints(record["scenario_id"])
            record["external_fields"] = self.list_external_fields(record["scenario_id"])
        else:
            counts = self._scenario_repository.count_items(record["scenario_id"])
            record["obstacle_count"] = counts["obstacles"]
            record["constraint_count"] = counts["constraints"]
            record["external_field_count"] = counts["fields"]
        return record

    def upsert_scenario(
        self,
        request: ScenarioCreate,
        *,
        built_in: bool = False,
        replace_items: bool = True,
        write_file: bool = True,
    ) -> dict[str, Any]:
        self._scenario_repository.upsert(request, built_in=built_in)
        if replace_items:
            self._scenario_repository.delete_items(request.scenario_id)
        if replace_items:
            for item in request.obstacles:
                self.create_obstacle(request.scenario_id, item, touch_scenario=False)
            for item in request.constraints:
                self.create_constraint(request.scenario_id, item, touch_scenario=False)
            for item in request.external_fields:
                self.create_external_field(
                    request.scenario_id, item, touch_scenario=False
                )
        scenario = self.get_scenario(request.scenario_id)
        if scenario is None:
            raise RuntimeError("Scenario was not persisted")
        if write_file:
            self.write_scenario_file(request.scenario_id)
        return scenario

    def update_scenario(
        self, scenario_id: str, request: ScenarioUpdate
    ) -> dict[str, Any] | None:
        current = self.get_scenario(scenario_id)
        if current is None:
            return None
        updates = request.model_dump(exclude_unset=True, mode="json")
        for key, value in updates.items():
            current[key] = value
        model = ScenarioCreate.model_validate(
            {
                **{
                    k: current[k]
                    for k in (
                        "scenario_id",
                        "name",
                        "description",
                        "coordinate_frame",
                        "origin",
                        "default_duration_s",
                        "motion",
                        "obstacle_avoidance",
                        "sensor_rates_hz",
                        "quality",
                        "faults",
                        "metadata",
                        "enabled",
                    )
                },
                "obstacles": current.get("obstacles", []),
                "constraints": current.get("constraints", []),
                "external_fields": current.get("external_fields", []),
            }
        )
        return self.upsert_scenario(
            model, built_in=bool(current.get("built_in")), replace_items=True
        )

    def delete_scenario(self, scenario_id: str) -> bool:
        current = self.get_scenario(scenario_id, include_items=False)
        if current is not None and current.get("built_in"):
            raise ValueError(
                "Built-in scenarios cannot be deleted; copy or disable the scenario instead"
            )
        if self._scenario_repository.simulation_run_count(scenario_id) > 0:
            raise ValueError(
                "Scenario is referenced by simulation runs and cannot be deleted"
            )
        deleted = self._scenario_repository.delete(scenario_id)
        if deleted:
            path = self.scenarios_dir / f"{scenario_id}.json"
            path.unlink(missing_ok=True)
        return deleted

    def write_scenario_file(
        self,
        scenario_id: str,
        target: Path | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> Path:
        data = snapshot or self.get_scenario(scenario_id)
        if data is None:
            raise FileNotFoundError(f"Scenario not found: {scenario_id}")
        path = target or (self.scenarios_dir / f"{scenario_id}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        export = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "built_in",
                "version",
                "created_at_utc",
                "updated_at_utc",
                "obstacle_count",
                "constraint_count",
                "external_field_count",
            }
        }
        path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
        return path

    def _touch(self, scenario_id: str) -> None:
        self._scenario_repository.touch(scenario_id)

    # ------------------------------------------------------------------
    # Environment objects
    # ------------------------------------------------------------------
    def _ensure_scenario(self, scenario_id: str) -> None:
        if self.get_scenario(scenario_id, include_items=False) is None:
            raise LookupError("Scenario not found")

    def create_obstacle(
        self, scenario_id: str, request: ObstacleCreate, *, touch_scenario: bool = True
    ) -> dict[str, Any]:
        self._ensure_scenario(scenario_id)
        item_id = request.obstacle_id or self._id("OBS")
        result = self._obstacle_repository.create(scenario_id, item_id, request)
        if touch_scenario:
            self._touch(scenario_id)
            self.write_scenario_file(scenario_id)
        return result

    def list_obstacles(self, scenario_id: str) -> list[dict[str, Any]]:
        return self._obstacle_repository.list_for_scenario(scenario_id)

    def get_obstacle(self, item_id: str) -> dict[str, Any] | None:
        return self._obstacle_repository.get(item_id)

    def update_obstacle(
        self, item_id: str, request: ObstacleUpdate
    ) -> dict[str, Any] | None:
        current = self.get_obstacle(item_id)
        if current is None:
            return None
        data = {**current, **request.model_dump(exclude_unset=True, mode="json")}
        replacement = ObstacleCreate.model_validate(
            {key: data.get(key) for key in ObstacleCreate.model_fields}
        )
        self._obstacle_repository.delete(item_id)
        replacement.obstacle_id = item_id
        return self.create_obstacle(current["scenario_id"], replacement)

    def delete_obstacle(self, item_id: str) -> bool:
        current = self.get_obstacle(item_id)
        if current is None:
            return False
        deleted = self._obstacle_repository.delete(item_id)
        if deleted:
            self._touch(current["scenario_id"])
            self.write_scenario_file(current["scenario_id"])
        return deleted

    def create_constraint(
        self,
        scenario_id: str,
        request: EnvironmentConstraintCreate,
        *,
        touch_scenario: bool = True,
    ) -> dict[str, Any]:
        self._ensure_scenario(scenario_id)
        item_id = request.constraint_id or self._id("CON")
        result = self._constraint_repository.create(scenario_id, item_id, request)
        if touch_scenario:
            self._touch(scenario_id)
            self.write_scenario_file(scenario_id)
        return result

    def list_constraints(self, scenario_id: str) -> list[dict[str, Any]]:
        return self._constraint_repository.list_for_scenario(scenario_id)

    def get_constraint(self, item_id: str) -> dict[str, Any] | None:
        return self._constraint_repository.get(item_id)

    def update_constraint(
        self, item_id: str, request: EnvironmentConstraintUpdate
    ) -> dict[str, Any] | None:
        current = self.get_constraint(item_id)
        if current is None:
            return None
        data = {**current, **request.model_dump(exclude_unset=True, mode="json")}
        replacement = EnvironmentConstraintCreate.model_validate(
            {
                key: data.get(key)
                for key in EnvironmentConstraintCreate.model_fields
            }
        )
        self._constraint_repository.delete(item_id)
        replacement.constraint_id = item_id
        return self.create_constraint(current["scenario_id"], replacement)

    def delete_constraint(self, item_id: str) -> bool:
        current = self.get_constraint(item_id)
        if current is None:
            return False
        deleted = self._constraint_repository.delete(item_id)
        if deleted:
            self._touch(current["scenario_id"])
            self.write_scenario_file(current["scenario_id"])
        return deleted

    def create_external_field(
        self,
        scenario_id: str,
        request: ExternalFieldCreate,
        *,
        touch_scenario: bool = True,
    ) -> dict[str, Any]:
        self._ensure_scenario(scenario_id)
        item_id = request.field_id or self._id("FIELD")
        result = self._external_field_repository.create(
            scenario_id,
            item_id,
            request,
        )
        if touch_scenario:
            self._touch(scenario_id)
            self.write_scenario_file(scenario_id)
        return result

    def list_external_fields(self, scenario_id: str) -> list[dict[str, Any]]:
        return self._external_field_repository.list_for_scenario(scenario_id)

    def get_external_field(self, item_id: str) -> dict[str, Any] | None:
        return self._external_field_repository.get(item_id)

    def update_external_field(
        self, item_id: str, request: ExternalFieldUpdate
    ) -> dict[str, Any] | None:
        current = self.get_external_field(item_id)
        if current is None:
            return None
        data = {**current, **request.model_dump(exclude_unset=True, mode="json")}
        replacement = ExternalFieldCreate.model_validate(
            {key: data.get(key) for key in ExternalFieldCreate.model_fields}
        )
        self._external_field_repository.delete(item_id)
        replacement.field_id = item_id
        return self.create_external_field(current["scenario_id"], replacement)

    def delete_external_field(self, item_id: str) -> bool:
        current = self.get_external_field(item_id)
        if current is None:
            return False
        deleted = self._external_field_repository.delete(item_id)
        if deleted:
            self._touch(current["scenario_id"])
            self.write_scenario_file(current["scenario_id"])
        return deleted

    # ------------------------------------------------------------------
    # Applicability and immutable mission snapshots
    # ------------------------------------------------------------------
    @staticmethod
    def applies(
        item: dict[str, Any],
        vehicle_id: str,
        vehicle_type: str,
        capabilities: dict[str, bool],
    ) -> bool:
        vehicle_types = item.get("applies_to_vehicle_types") or []
        vehicle_ids = item.get("applies_to_vehicle_ids") or []
        required = item.get("required_capabilities") or []
        if vehicle_types and vehicle_type not in vehicle_types:
            return False
        if vehicle_ids and vehicle_id not in vehicle_ids:
            return False
        return all(bool(capabilities.get(name)) for name in required)

    def build_snapshot(
        self,
        scenario_id: str,
        *,
        mission_id: str,
        vehicle_id: str,
        vehicle_type: str,
        capabilities: dict[str, bool],
        vehicle_profile_id: str,
        effective_parameters: dict[str, Any],
        random_seed: int,
    ) -> dict[str, Any]:
        scenario = self.get_scenario(scenario_id)
        if scenario is None:
            raise LookupError("Scenario not found")
        snapshot = {
            **{
                key: scenario[key]
                for key in (
                    "scenario_id",
                    "name",
                    "description",
                    "coordinate_frame",
                    "origin",
                    "default_duration_s",
                    "motion",
                    "obstacle_avoidance",
                    "sensor_rates_hz",
                    "quality",
                    "faults",
                    "metadata",
                    "version",
                )
            },
            "mission_id": mission_id,
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "vehicle_profile_id": vehicle_profile_id,
            "vehicle_capabilities": capabilities,
            "effective_vehicle_parameters": effective_parameters,
            "random_seed": random_seed,
            "obstacles": [
                item
                for item in scenario["obstacles"]
                if self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "constraints": [
                item
                for item in scenario["constraints"]
                if item.get("enabled", True)
                and self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "external_fields": [
                item
                for item in scenario["external_fields"]
                if item.get("enabled", True)
                and self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "snapshot_created_at_utc": self._now(),
        }
        canonical = self._json(snapshot).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        self._mission_environment_snapshot_repository.save(
            mission_id=mission_id,
            scenario_id=scenario_id,
            scenario_version=int(scenario["version"]),
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            snapshot_json=canonical.decode("utf-8"),
            sha256=digest,
            created_at_utc=self._now(),
        )
        snapshot["sha256"] = digest
        return snapshot

    def capture_snapshot_payload(
        self,
        *,
        mission_id: str,
        vehicle_id: str,
        vehicle_type: str,
        scenario_payload: dict[str, Any],
        capabilities: dict[str, bool],
        vehicle_profile_id: str,
        effective_parameters: dict[str, Any],
        random_seed: int,
    ) -> dict[str, Any]:
        raw = dict(scenario_payload)
        raw.setdefault("scenario_id", raw.get("name", "inline-scenario"))
        raw.setdefault("name", str(raw["scenario_id"]))
        raw.setdefault("description", "")
        raw.setdefault("coordinate_frame", "LOCAL_ENU")
        raw.setdefault("origin", {})
        raw.setdefault("default_duration_s", 60.0)
        raw.setdefault("motion", {})
        raw.setdefault("obstacle_avoidance", {})
        raw.setdefault("sensor_rates_hz", {})
        raw.setdefault("quality", {})
        raw.setdefault("faults", {})
        raw.setdefault("obstacles", [])
        raw.setdefault("constraints", [])
        raw.setdefault("external_fields", [])
        raw.setdefault("metadata", {})
        raw.setdefault("enabled", True)
        model = ScenarioCreate.model_validate(raw)
        scenario = model.model_dump(mode="json")
        snapshot = {
            **{
                key: scenario[key]
                for key in (
                    "scenario_id",
                    "name",
                    "description",
                    "coordinate_frame",
                    "origin",
                    "default_duration_s",
                    "motion",
                    "obstacle_avoidance",
                    "sensor_rates_hz",
                    "quality",
                    "faults",
                    "metadata",
                )
            },
            "version": int(raw.get("version", 1) or 1),
            "mission_id": mission_id,
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "vehicle_profile_id": vehicle_profile_id,
            "vehicle_capabilities": capabilities,
            "effective_vehicle_parameters": effective_parameters,
            "random_seed": random_seed,
            "obstacles": [
                item
                for item in scenario["obstacles"]
                if self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "constraints": [
                item
                for item in scenario["constraints"]
                if item.get("enabled", True)
                and self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "external_fields": [
                item
                for item in scenario["external_fields"]
                if item.get("enabled", True)
                and self.applies(item, vehicle_id, vehicle_type, capabilities)
            ],
            "snapshot_created_at_utc": self._now(),
        }
        canonical = self._json(snapshot).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        self._mission_environment_snapshot_repository.save(
            mission_id=mission_id,
            scenario_id=snapshot["scenario_id"],
            scenario_version=int(snapshot["version"]),
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            snapshot_json=canonical.decode("utf-8"),
            sha256=digest,
            created_at_utc=self._now(),
        )
        snapshot["sha256"] = digest
        return snapshot

    def get_mission_environment(self, mission_id: str) -> dict[str, Any] | None:
        return self._mission_environment_snapshot_repository.get_by_mission_id(
            mission_id
        )
