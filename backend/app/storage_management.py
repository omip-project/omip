from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_RETENTION_POLICY: dict[str, int] = {
    "raw_messages_days": 30,
    "telemetry_days": 180,
    "application_logs_days": 7,
    "system_snapshots_days": 7,
}


class StorageManager:
    """Storage lifecycle, pagination, export-job and SQLite maintenance support."""

    def __init__(self, repository: Any, export_dir: Path, backup_dir: Path) -> None:
        self.repository = repository
        self.database_path = Path(repository._database_path)  # repository-owned local SQLite file
        self.export_dir = Path(export_dir)
        self.backup_dir = Path(backup_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _load_json(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _initialise(self) -> None:
        now = self._utc_now().isoformat()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS storage_settings (
                    setting_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS export_jobs (
                    job_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    export_format TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL,
                    started_at_utc TEXT,
                    completed_at_utc TEXT,
                    file_name TEXT,
                    file_path TEXT,
                    file_size_bytes INTEGER,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS storage_backups (
                    backup_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT,
                    file_name TEXT,
                    file_path TEXT,
                    file_size_bytes INTEGER,
                    sha256 TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_export_jobs_created
                    ON export_jobs(created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_export_jobs_mission
                    ON export_jobs(mission_id, created_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_storage_backups_created
                    ON storage_backups(created_at_utc DESC);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO storage_settings(setting_key, value_json, updated_at_utc)
                VALUES ('retention_policy', ?, ?)
                """,
                (json.dumps(DEFAULT_RETENTION_POLICY, separators=(",", ":")), now),
            )

    # ------------------------------------------------------------------
    # Storage overview
    # ------------------------------------------------------------------
    def table_statistics(self) -> list[dict[str, Any]]:
        excluded = {"sqlite_sequence"}
        results: list[dict[str, Any]] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            for row in rows:
                name = str(row["name"])
                if name in excluded or not re.fullmatch(r"[A-Za-z0-9_]+", name):
                    continue
                count = int(connection.execute(f'SELECT COUNT(*) AS c FROM "{name}"').fetchone()["c"])
                results.append({"table_name": name, "row_count": count})
        return results

    def storage_summary(self) -> dict[str, Any]:
        table_rows = {item["table_name"]: item["row_count"] for item in self.table_statistics()}
        database_size = self.database_path.stat().st_size if self.database_path.exists() else 0
        now = self._utc_now()
        since = (now - timedelta(days=1)).isoformat()
        with self._connect() as connection:
            raw_24h = int(connection.execute(
                "SELECT COUNT(*) AS c FROM raw_sensor_messages WHERE received_at_utc >= ?", (since,)
            ).fetchone()["c"])
            telemetry_24h = int(connection.execute(
                "SELECT COUNT(*) AS c FROM telemetry WHERE received_at_utc >= ?", (since,)
            ).fetchone()["c"])
            time_bounds: dict[str, dict[str, str | None]] = {}
            for table, column in (
                ("raw_sensor_messages", "received_at_utc"),
                ("telemetry", "received_at_utc"),
                ("application_logs", "timestamp_utc"),
                ("system_metric_snapshots", "timestamp_utc"),
            ):
                row = connection.execute(
                    f'SELECT MIN("{column}") AS oldest, MAX("{column}") AS newest FROM "{table}"'
                ).fetchone()
                time_bounds[table] = {"oldest_utc": row["oldest"], "newest_utc": row["newest"]}

        measured_rows = sum(table_rows.get(name, 0) for name in ("raw_sensor_messages", "telemetry"))
        new_rows_24h = raw_24h + telemetry_24h
        estimated_daily_growth = 0
        if measured_rows > 0 and database_size > 0:
            estimated_daily_growth = int((database_size / measured_rows) * new_rows_24h)

        return {
            "captured_at_utc": now.isoformat(),
            "database_path": str(self.database_path),
            "database_size_bytes": database_size,
            "table_rows": table_rows,
            "mission_count": table_rows.get("missions", 0),
            "raw_messages_last_24h": raw_24h,
            "telemetry_last_24h": telemetry_24h,
            "estimated_daily_growth_bytes": estimated_daily_growth,
            "time_bounds": time_bounds,
            "retention_policy": self.get_retention_policy(),
            "export_directory": str(self.export_dir),
            "backup_directory": str(self.backup_dir),
        }

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    @staticmethod
    def _page_response(items: list[dict[str, Any]], page: int, page_size: int, total: int) -> dict[str, Any]:
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
        }

    def mission_telemetry_page(
        self,
        mission_id: str,
        page: int,
        page_size: int,
        sort_order: str = "asc",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        where = ["mission_id = ?"]
        params: list[Any] = [mission_id]
        if start_time:
            where.append("timestamp_utc >= ?")
            params.append(start_time)
        if end_time:
            where.append("timestamp_utc <= ?")
            params.append(end_time)
        where_sql = " AND ".join(where)
        direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) AS c FROM telemetry WHERE {where_sql}", params
            ).fetchone()["c"])
            rows = connection.execute(
                f"""
                SELECT payload_json FROM telemetry WHERE {where_sql}
                ORDER BY timestamp_utc {direction}, id {direction}
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return self._page_response([json.loads(row["payload_json"]) for row in rows], page, page_size, total)

    def mission_raw_page(
        self,
        mission_id: str,
        page: int,
        page_size: int,
        sort_order: str = "asc",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        where = ["mission_id = ?"]
        params: list[Any] = [mission_id]
        if start_time:
            where.append("timestamp_utc >= ?")
            params.append(start_time)
        if end_time:
            where.append("timestamp_utc <= ?")
            params.append(end_time)
        where_sql = " AND ".join(where)
        direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) AS c FROM raw_sensor_messages WHERE {where_sql}", params
            ).fetchone()["c"])
            rows = connection.execute(
                f"""
                SELECT payload_json FROM raw_sensor_messages WHERE {where_sql}
                ORDER BY timestamp_utc {direction}, id {direction}
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return self._page_response([json.loads(row["payload_json"]) for row in rows], page, page_size, total)

    def application_logs_page(self, page: int, page_size: int, level: str | None = None) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if level:
            where.append("level = ?")
            params.append(level.upper())
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) AS c FROM application_logs {where_sql}", params
            ).fetchone()["c"])
            rows = connection.execute(
                f"""
                SELECT * FROM application_logs {where_sql}
                ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["details"] = self._load_json(item.pop("details_json", "{}"))
            items.append(item)
        return self._page_response(items, page, page_size, total)

    # ------------------------------------------------------------------
    # Retention and cleanup
    # ------------------------------------------------------------------
    def get_retention_policy(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM storage_settings WHERE setting_key='retention_policy'"
            ).fetchone()
        policy = dict(DEFAULT_RETENTION_POLICY)
        policy.update({k: int(v) for k, v in self._load_json(row["value_json"] if row else None).items() if k in policy})
        return policy

    def update_retention_policy(self, updates: dict[str, Any]) -> dict[str, int]:
        policy = self.get_retention_policy()
        for key in policy:
            if key in updates and updates[key] is not None:
                value = int(updates[key])
                if value < 1 or value > 3650:
                    raise ValueError(f"{key} must be between 1 and 3650 days")
                policy[key] = value
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO storage_settings(setting_key, value_json, updated_at_utc)
                VALUES ('retention_policy', ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (json.dumps(policy, separators=(",", ":")), self._utc_now().isoformat()),
            )
        return policy

    def cleanup_preview(self) -> dict[str, Any]:
        policy = self.get_retention_policy()
        now = self._utc_now()
        cutoffs = {
            "raw_sensor_messages": (now - timedelta(days=policy["raw_messages_days"])).isoformat(),
            "telemetry": (now - timedelta(days=policy["telemetry_days"])).isoformat(),
            "application_logs": (now - timedelta(days=policy["application_logs_days"])).isoformat(),
            "system_metric_snapshots": (now - timedelta(days=policy["system_snapshots_days"])).isoformat(),
        }
        counts: dict[str, int] = {}
        with self._connect() as connection:
            counts["raw_sensor_messages"] = int(connection.execute(
                """
                SELECT COUNT(*) AS c FROM raw_sensor_messages r
                JOIN missions m ON m.mission_id=r.mission_id
                WHERE r.received_at_utc < ? AND m.status IN ('COMPLETED','ABORTED')
                """, (cutoffs["raw_sensor_messages"],)
            ).fetchone()["c"])
            counts["telemetry"] = int(connection.execute(
                """
                SELECT COUNT(*) AS c FROM telemetry t
                JOIN missions m ON m.mission_id=t.mission_id
                WHERE t.received_at_utc < ? AND m.status IN ('COMPLETED','ABORTED')
                """, (cutoffs["telemetry"],)
            ).fetchone()["c"])
            counts["application_logs"] = int(connection.execute(
                "SELECT COUNT(*) AS c FROM application_logs WHERE timestamp_utc < ?",
                (cutoffs["application_logs"],),
            ).fetchone()["c"])
            counts["system_metric_snapshots"] = int(connection.execute(
                "SELECT COUNT(*) AS c FROM system_metric_snapshots WHERE timestamp_utc < ?",
                (cutoffs["system_metric_snapshots"],),
            ).fetchone()["c"])
        return {
            "generated_at_utc": now.isoformat(),
            "policy": policy,
            "cutoffs": cutoffs,
            "eligible_rows": counts,
            "total_eligible_rows": sum(counts.values()),
            "execute_confirmation": "DELETE ELIGIBLE DATA",
            "automatic_cleanup_enabled": False,
        }

    def execute_cleanup(self, confirmation: str) -> dict[str, Any]:
        if confirmation != "DELETE ELIGIBLE DATA":
            raise ValueError("confirmation must exactly equal DELETE ELIGIBLE DATA")
        preview = self.cleanup_preview()
        cutoffs = preview["cutoffs"]
        deleted: dict[str, int] = {}
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM raw_sensor_messages
                WHERE received_at_utc < ? AND mission_id IN (
                    SELECT mission_id FROM missions WHERE status IN ('COMPLETED','ABORTED')
                )
                """, (cutoffs["raw_sensor_messages"],)
            )
            deleted["raw_sensor_messages"] = cursor.rowcount
            cursor = connection.execute(
                """
                DELETE FROM telemetry
                WHERE received_at_utc < ? AND mission_id IN (
                    SELECT mission_id FROM missions WHERE status IN ('COMPLETED','ABORTED')
                )
                """, (cutoffs["telemetry"],)
            )
            deleted["telemetry"] = cursor.rowcount
            cursor = connection.execute(
                "DELETE FROM application_logs WHERE timestamp_utc < ?", (cutoffs["application_logs"],)
            )
            deleted["application_logs"] = cursor.rowcount
            cursor = connection.execute(
                "DELETE FROM system_metric_snapshots WHERE timestamp_utc < ?",
                (cutoffs["system_metric_snapshots"],),
            )
            deleted["system_metric_snapshots"] = cursor.rowcount
        return {
            "executed_at_utc": self._utc_now().isoformat(),
            "deleted_rows": deleted,
            "total_deleted_rows": sum(max(value, 0) for value in deleted.values()),
        }

    # ------------------------------------------------------------------
    # Mission deletion
    # ------------------------------------------------------------------
    def mission_delete_preview(self, mission_id: str) -> dict[str, Any] | None:
        mission = self.repository.get_mission(mission_id)
        if mission is None:
            return None
        tables = {
            "alerts": "alerts",
            "integrity_events": "integrity_events",
            "mission_events": "mission_events",
            "obstacle_interactions": "obstacle_interactions",
            "obstacle_interaction_state": "obstacle_interaction_state",
            "vehicle_heartbeats": "vehicle_heartbeats",
            "raw_sensor_messages": "raw_sensor_messages",
            "telemetry": "telemetry",
        }
        counts: dict[str, int] = {}
        with self._connect() as connection:
            for key, table in tables.items():
                counts[key] = int(connection.execute(
                    f'SELECT COUNT(*) AS c FROM "{table}" WHERE mission_id = ?', (mission_id,)
                ).fetchone()["c"])
        estimated_bytes = 0
        database_size = self.database_path.stat().st_size if self.database_path.exists() else 0
        total_db_rows = sum(item["row_count"] for item in self.table_statistics())
        if total_db_rows:
            estimated_bytes = int(database_size * (sum(counts.values()) + 1) / total_db_rows)
        return {
            "mission": mission,
            "related_rows": counts,
            "total_related_rows": sum(counts.values()),
            "estimated_released_bytes": estimated_bytes,
            "confirmation_value": mission_id,
            "warning": "This operation permanently deletes the Mission and all linked operational data.",
        }

    def delete_mission(self, mission_id: str, confirmation: str) -> dict[str, Any] | None:
        preview = self.mission_delete_preview(mission_id)
        if preview is None:
            return None
        if confirmation != mission_id:
            raise ValueError("confirmation must exactly match mission_id")
        order = [
            "alerts", "integrity_events", "mission_events", "obstacle_interaction_state",
            "obstacle_interactions", "vehicle_heartbeats", "raw_sensor_messages", "telemetry",
        ]
        deleted: dict[str, int] = {}
        with self._lock, self._connect() as connection:
            for table in order:
                cursor = connection.execute(f'DELETE FROM "{table}" WHERE mission_id = ?', (mission_id,))
                deleted[table] = cursor.rowcount
            cursor = connection.execute("DELETE FROM missions WHERE mission_id = ?", (mission_id,))
            deleted["missions"] = cursor.rowcount
        return {
            "mission_id": mission_id,
            "deleted_at_utc": self._utc_now().isoformat(),
            "deleted_rows": deleted,
            "total_deleted_rows": sum(max(value, 0) for value in deleted.values()),
        }

    # ------------------------------------------------------------------
    # Export jobs
    # ------------------------------------------------------------------
    def create_export_job(self, mission_id: str, export_format: str) -> dict[str, Any]:
        if self.repository.get_mission(mission_id) is None:
            raise LookupError("Mission not found")
        if export_format not in {"package", "telemetry_csv", "telemetry_jsonl", "raw_csv", "raw_jsonl"}:
            raise ValueError("Unsupported export format")
        job_id = f"EXPORT-{uuid4().hex.upper()}"
        now = self._utc_now().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO export_jobs(
                    job_id, mission_id, export_format, state, progress_percent, created_at_utc
                ) VALUES (?, ?, ?, 'QUEUED', 0, ?)
                """, (job_id, mission_id, export_format, now)
            )
        return self.get_export_job(job_id) or {}

    @staticmethod
    def _decode_export_job(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = StorageManager._load_json(result.pop("metadata_json", "{}"))
        result["download_ready"] = result.get("state") == "COMPLETED" and bool(result.get("file_path"))
        return result

    def get_export_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM export_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._decode_export_job(row) if row else None

    def list_export_jobs(self, mission_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if mission_id:
                rows = connection.execute(
                    "SELECT * FROM export_jobs WHERE mission_id=? ORDER BY created_at_utc DESC LIMIT ?",
                    (mission_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM export_jobs ORDER BY created_at_utc DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._decode_export_job(row) for row in rows]

    def mark_export_running(self, job_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE export_jobs SET state='RUNNING', progress_percent=10, started_at_utc=? WHERE job_id=?",
                (self._utc_now().isoformat(), job_id),
            )

    def complete_export_job(self, job_id: str, file_path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        file_path = Path(file_path)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE export_jobs SET state='COMPLETED', progress_percent=100,
                    completed_at_utc=?, file_name=?, file_path=?, file_size_bytes=?,
                    error_message=NULL, metadata_json=?
                WHERE job_id=?
                """,
                (
                    self._utc_now().isoformat(), file_path.name, str(file_path),
                    file_path.stat().st_size, json.dumps(metadata or {}, separators=(",", ":")), job_id,
                ),
            )
        return self.get_export_job(job_id) or {}

    def fail_export_job(self, job_id: str, error: str) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE export_jobs SET state='FAILED', completed_at_utc=?, error_message=?
                WHERE job_id=?
                """, (self._utc_now().isoformat(), error[:4000], job_id)
            )
        return self.get_export_job(job_id) or {}

    # ------------------------------------------------------------------
    # Backups and maintenance
    # ------------------------------------------------------------------
    def create_backup(self, label: str = "manual") -> dict[str, Any]:
        backup_id = f"BACKUP-{uuid4().hex.upper()}"
        safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label or "manual")[:80]
        now = self._utc_now()
        file_name = f"omip-{now.strftime('%Y%m%dT%H%M%SZ')}-{safe_label}.db"
        output_path = self.backup_dir / file_name
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO storage_backups(backup_id, label, state, created_at_utc)
                VALUES (?, ?, 'RUNNING', ?)
                """, (backup_id, label or "manual", now.isoformat())
            )
        try:
            source = sqlite3.connect(self.database_path, timeout=30.0)
            target = sqlite3.connect(output_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    UPDATE storage_backups SET state='COMPLETED', completed_at_utc=?,
                        file_name=?, file_path=?, file_size_bytes=?, sha256=?
                    WHERE backup_id=?
                    """,
                    (self._utc_now().isoformat(), file_name, str(output_path), output_path.stat().st_size, digest, backup_id),
                )
        except Exception as exc:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "UPDATE storage_backups SET state='FAILED', completed_at_utc=?, error_message=? WHERE backup_id=?",
                    (self._utc_now().isoformat(), str(exc)[:4000], backup_id),
                )
        return self.get_backup(backup_id) or {}

    @staticmethod
    def _decode_backup(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = StorageManager._load_json(result.pop("metadata_json", "{}"))
        result["download_ready"] = result.get("state") == "COMPLETED" and bool(result.get("file_path"))
        return result

    def get_backup(self, backup_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM storage_backups WHERE backup_id=?", (backup_id,)).fetchone()
        return self._decode_backup(row) if row else None

    def list_backups(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM storage_backups ORDER BY created_at_utc DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode_backup(row) for row in rows]

    def integrity_check(self) -> dict[str, Any]:
        started = self._utc_now()
        with self._connect() as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        messages = [str(row[0]) for row in rows]
        return {
            "status": "OK" if messages == ["ok"] else "ERROR",
            "messages": messages,
            "checked_at_utc": started.isoformat(),
        }

    def analyze(self) -> dict[str, Any]:
        started = self._utc_now()
        with self._lock, self._connect() as connection:
            connection.execute("ANALYZE")
        return {"operation": "ANALYZE", "status": "COMPLETED", "completed_at_utc": started.isoformat()}

    def checkpoint(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return {
            "operation": "WAL_CHECKPOINT",
            "status": "COMPLETED",
            "busy": int(row[0]) if row else 0,
            "log_frames": int(row[1]) if row else 0,
            "checkpointed_frames": int(row[2]) if row else 0,
            "completed_at_utc": self._utc_now().isoformat(),
        }

    def vacuum(self) -> dict[str, Any]:
        started = self._utc_now()
        with self._lock:
            connection = sqlite3.connect(self.database_path, timeout=30.0, isolation_level=None)
            try:
                connection.execute("VACUUM")
            finally:
                connection.close()
        return {
            "operation": "VACUUM",
            "status": "COMPLETED",
            "completed_at_utc": self._utc_now().isoformat(),
            "database_size_bytes": self.database_path.stat().st_size if self.database_path.exists() else 0,
        }


def build_export_content(repository: Any, mission_id: str, export_format: str) -> tuple[bytes, str, str]:
    """Build an export payload and return bytes, filename, and media type."""
    mission = repository.get_mission(mission_id)
    if mission is None:
        raise LookupError("Mission not found")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", mission_id)
    telemetry_records = repository.mission_history(mission_id)
    raw_records = repository.raw_history(mission_id=mission_id, limit=1_000_000)

    if export_format == "telemetry_jsonl":
        text = "\n".join(json.dumps(item, separators=(",", ":")) for item in telemetry_records)
        return ((text + "\n") if text else "").encode("utf-8"), f"{safe_id}.jsonl", "application/x-ndjson"

    if export_format == "telemetry_csv":
        output = io.StringIO(newline="")
        flattened = repository.flatten_for_csv(telemetry_records)
        if flattened:
            writer = csv.DictWriter(output, fieldnames=list(flattened[0].keys()))
            writer.writeheader(); writer.writerows(flattened)
        else:
            output.write("mission_id\n")
        return output.getvalue().encode("utf-8"), f"{safe_id}.csv", "text/csv"

    if export_format in {"raw_jsonl", "raw_csv"}:
        if export_format == "raw_jsonl":
            text = "\n".join(json.dumps(item, separators=(",", ":")) for item in raw_records)
            return ((text + "\n") if text else "").encode("utf-8"), f"{safe_id}-raw.jsonl", "application/x-ndjson"
        fields = [
            "message_id", "vehicle_id", "sensor_id", "mission_id", "sequence_no",
            "timestamp_utc", "received_at_utc", "latency_ms", "message_type",
            "transport", "topic", "valid", "confidence", "payload_json",
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
        for item in raw_records:
            writer.writerow({
                **{key: item.get(key) for key in fields if key not in {"valid", "confidence", "payload_json"}},
                "valid": item.get("quality", {}).get("valid"),
                "confidence": item.get("quality", {}).get("confidence"),
                "payload_json": json.dumps(item.get("payload", {}), separators=(",", ":")),
            })
        return output.getvalue().encode("utf-8"), f"{safe_id}-raw.csv", "text/csv"

    if export_format != "package":
        raise ValueError("Unsupported export format")

    events = repository.list_events(mission_id)
    integrity_events = repository.list_integrity_events(mission_id=mission_id, limit=1_000_000)
    alerts = repository.list_alerts(mission_id=mission_id, limit=100_000)
    quality = repository.quality_summary(mission_id) or {}
    integrity_metrics = repository.mission_integrity_metrics(mission_id) or {}
    environment = {}
    obstacle_interactions: list[dict[str, Any]] = []
    try:
        connection = sqlite3.connect(repository._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM obstacle_interactions WHERE mission_id=? ORDER BY timestamp_utc",
            (mission_id,),
        ).fetchall()
        for row in rows:
            item = dict(row)
            item["avoidance_active"] = bool(item.get("avoidance_active"))
            try:
                item["details"] = json.loads(item.pop("details_json", "{}") or "{}")
            except json.JSONDecodeError:
                item["details"] = {}
            obstacle_interactions.append(item)
        connection.close()
    except sqlite3.Error:
        obstacle_interactions = []
    try:
        connection = sqlite3.connect(repository._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT snapshot_json, sha256, scenario_version, created_at_utc FROM mission_environment_snapshots WHERE mission_id = ?", (mission_id,)).fetchone()
        connection.close()
        if row:
            environment = json.loads(row["snapshot_json"] or "{}")
            environment["sha256"] = row["sha256"]
            environment["scenario_version"] = row["scenario_version"]
            environment["created_at_utc"] = row["created_at_utc"]
    except sqlite3.Error:
        environment = {}

    telemetry_jsonl, _, _ = build_export_content(repository, mission_id, "telemetry_jsonl")
    telemetry_csv, _, _ = build_export_content(repository, mission_id, "telemetry_csv")
    raw_jsonl, _, _ = build_export_content(repository, mission_id, "raw_jsonl")
    raw_csv, _, _ = build_export_content(repository, mission_id, "raw_csv")

    package = io.BytesIO()
    with zipfile.ZipFile(package, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mission.json", json.dumps(mission, indent=2))
        archive.writestr("quality.json", json.dumps(quality, indent=2))
        archive.writestr("events.json", json.dumps(events, indent=2))
        archive.writestr("integrity-events.json", json.dumps(integrity_events, indent=2))
        archive.writestr("integrity-metrics.json", json.dumps(integrity_metrics, indent=2))
        archive.writestr("alerts.json", json.dumps(alerts, indent=2))
        archive.writestr("environment.json", json.dumps(environment, indent=2))
        archive.writestr("obstacle-interactions.json", json.dumps(obstacle_interactions, indent=2))
        archive.writestr("telemetry.csv", telemetry_csv)
        archive.writestr("telemetry.jsonl", telemetry_jsonl)
        archive.writestr("raw-messages.csv", raw_csv)
        archive.writestr("raw-messages.jsonl", raw_jsonl)
    return package.getvalue(), f"{safe_id}-omip-export.zip", "application/zip"
