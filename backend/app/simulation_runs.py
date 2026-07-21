from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import OmipRepository
from .schemas import SimulationRunCreate


class SimulationRunManager:
    """Launch and supervise local OMIP simulator workers.

    The manager is intentionally local-process based for the starter platform. A
    later deployment may replace it with a container or distributed job runner
    without changing the REST contract or persisted run configuration.
    """

    def __init__(
        self,
        repository: OmipRepository,
        project_dir: Path,
        api_base: str = "http://127.0.0.1:8000",
    ) -> None:
        self.repository = repository
        self.project_dir = project_dir
        self.api_base = api_base.rstrip("/")
        self.logs_dir = project_dir / "backend" / "storage" / "simulation-logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._log_handles: dict[str, Any] = {}

    @staticmethod
    def generated_run_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"SIMRUN-{stamp}-{uuid4().hex[:6].upper()}"

    @staticmethod
    def generated_mission_id(vehicle_id: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        suffix = uuid4().hex[:5].upper()
        return f"MISSION-{vehicle_id}-{stamp}-{suffix}"

    def scenario_path(self, scenario_id: str) -> Path:
        path = self.project_dir / "scenarios" / f"{scenario_id}.json"
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Scenario not found: {scenario_id}")
        return path

    def create(
        self,
        request: SimulationRunCreate,
        effective_parameters: dict[str, Any],
        scenario_path_override: Path | None = None,
    ) -> dict[str, Any]:
        run_id = self.generated_run_id()
        mission_id = request.mission_id or self.generated_mission_id(request.vehicle_id)
        scenario_path = scenario_path_override or self.scenario_path(request.scenario_id)
        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario not found: {request.scenario_id}")
        record = self.repository.create_simulation_run_record(
            run_id, request, mission_id, effective_parameters
        )
        if not request.launch_process:
            return record
        return self._launch(run_id, request, mission_id, scenario_path)

    def _build_command(
        self,
        run_id: str,
        request: SimulationRunCreate,
        mission_id: str,
        scenario_path: Path,
    ) -> list[str]:
        command = [
            sys.executable,
            str(self.project_dir / "simulator" / "multi_sensor_simulator.py"),
            "--api-base", self.api_base,
            "--vehicle-id", request.vehicle_id,
            "--vehicle-type", request.vehicle_type,
            "--vehicle-profile", request.vehicle_profile_id,
            "--scenario", str(scenario_path),
            "--mission-id", mission_id,
            "--duration", str(request.duration_s),
            "--transport", request.transport,
            "--random-seed", str(request.random_seed),
            "--simulation-run-id", run_id,
        ]
        if request.parameter_overrides:
            import json
            command.extend(["--parameter-overrides", json.dumps(request.parameter_overrides, separators=(",", ":"))])
        return command

    def _launch(
        self,
        run_id: str,
        request: SimulationRunCreate,
        mission_id: str,
        scenario_path: Path,
    ) -> dict[str, Any]:
        command = self._build_command(run_id, request, mission_id, scenario_path)
        log_path = self.logs_dir / f"{run_id}.log"
        log_handle = log_path.open("a", encoding="utf-8", buffering=1)
        creationflags = 0
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            self.repository.update_simulation_run(
                run_id,
                status="STARTING",
                command=command,
                log_path=str(log_path),
            )
            process = subprocess.Popen(
                command,
                cwd=self.project_dir,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                **kwargs,
            )
        except Exception as exc:
            log_handle.close()
            self.repository.update_simulation_run(
                run_id,
                status="FAILED",
                command=command,
                error_message=str(exc),
                log_path=str(log_path),
                mark_ended=True,
            )
            raise

        with self._lock:
            self._processes[run_id] = process
            self._log_handles[run_id] = log_handle
        self.repository.update_simulation_run(
            run_id,
            status="RUNNING",
            process_id=process.pid,
            command=command,
            log_path=str(log_path),
            mark_started=True,
        )
        thread = threading.Thread(
            target=self._monitor,
            args=(run_id, process),
            name=f"omip-simulation-{run_id}",
            daemon=True,
        )
        thread.start()
        result = self.repository.get_simulation_run(run_id)
        if result is None:
            raise RuntimeError("Simulation run disappeared after launch")
        return result

    def _monitor(self, run_id: str, process: subprocess.Popen[Any]) -> None:
        exit_code = process.wait()
        current = self.repository.get_simulation_run(run_id) or {}
        current_status = current.get("status")
        if current_status == "STOPPING":
            final_status = "ABORTED"
        elif exit_code == 0:
            final_status = "COMPLETED"
        else:
            final_status = "FAILED"
        self.repository.update_simulation_run(
            run_id,
            status=final_status,
            exit_code=exit_code,
            error_message=None if exit_code == 0 else f"Simulator exited with code {exit_code}",
            mark_ended=True,
        )
        with self._lock:
            self._processes.pop(run_id, None)
            handle = self._log_handles.pop(run_id, None)
        if handle is not None:
            handle.close()

    def stop(self, run_id: str, reason: str = "Stopped by operator") -> dict[str, Any] | None:
        record = self.repository.get_simulation_run(run_id)
        if record is None:
            return None
        if record["status"] not in {"STARTING", "RUNNING", "STOPPING"}:
            return record
        self.repository.update_simulation_run(
            run_id,
            status="STOPPING",
            stop_reason=reason,
        )
        with self._lock:
            process = self._processes.get(run_id)
        if process is None or process.poll() is not None:
            return self.repository.update_simulation_run(
                run_id,
                status="ABORTED",
                stop_reason=reason,
                mark_ended=True,
            )
        try:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
        except Exception:
            process.kill()
        return self.repository.get_simulation_run(run_id)

    def stop_all(self) -> None:
        with self._lock:
            run_ids = list(self._processes)
        for run_id in run_ids:
            try:
                self.stop(run_id, "OMIP service is shutting down")
            except Exception:
                pass
