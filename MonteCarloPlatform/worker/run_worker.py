"""The one-run worker lifecycle.

The worker receives one self-contained ``WorkerInput`` and owns its complete
EMTP lifecycle.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
from time import perf_counter

from com_client import EmtpComClient
from emtp_utils import Design, Simulation
from MonteCarloPlatform.worker.plant_setter import PlantSetter, PlantSetterReport
from MonteCarloPlatform.worker.result import WorkerResult
from MonteCarloPlatform.worker.task import WorkerInput
from MonteCarloPlatform.worker.workspace import PreparedRunWorkspace, RunWorkspace

LOGGER = logging.getLogger(__name__)


class RunWorker:
    """Execute the currently implemented stages for one run task."""

    def __init__(self) -> None:

        self._emtp_client: EmtpComClient | None = None
        self._emtp_object = None
        self._design_is_open = False
        self._run_log_handler: logging.FileHandler | None = None

    def execute(self, worker_input: WorkerInput) -> WorkerResult:
        started_at = datetime.now().astimezone()
        started_timer = perf_counter()
        execution_id = f"{worker_input.study_id}_{worker_input.run_name}"
        run_label = f"Run {worker_input.run_name}"
        workspace: PreparedRunWorkspace | None = None
        LOGGER.info("%s: starting.", run_label)

        try:
            workspace = self._preparing_workspace(worker_input)
            self._update_status(workspace, "workspace_ready")
            self._configure_run_logging(workspace)
            LOGGER.info("%s: workspace prepared.", run_label)

            LOGGER.info("%s: starting EMTP.", run_label)
            self._start_emtp()
            self._update_status(workspace, "emtp_started")

            LOGGER.info(
                "%s: opening design '%s'.", run_label, workspace.model_path.name
            )
            self._open_design(workspace)
            self._update_status(workspace, "design_opened")

            LOGGER.info(
                "%s: applying parameters to %d units.",
                run_label,
                len(worker_input.units),
            )
            report = self._apply_parameters(worker_input)
            self._update_status(
                workspace,
                "parameters_applied",
                parameterized_devices=len(report.changes),
            )
            LOGGER.info(
                "%s: parameters applied to %d devices.", run_label, len(report.changes)
            )

            LOGGER.info("%s: saving parameterized design.", run_label)
            self._save_design_after_parameterization()
            self._update_status(workspace, "saved_before_simulation")

            LOGGER.info("%s: running load flow.", run_label)
            self._run_load_flow()
            self._update_status(workspace, "load_flow_completed")
            LOGGER.info("%s: load flow completed.", run_label)

            tmax = worker_input.simulation.get("tmax", 10.0)
            LOGGER.info(
                "%s: running time-domain simulation (tmax=%s).",
                run_label,
                tmax,
            )
            self._run_time_domain_simulation(worker_input)
            self._update_status(workspace, "time_domain_completed")
            LOGGER.info("%s: time-domain simulation completed.", run_label)

            LOGGER.info("%s: saving final design.", run_label)
            self._save_design_after_simulation()
            self._update_status(workspace, "saved_after_simulation")

            LOGGER.info("%s: closing EMTP.", run_label)
            self._close_design_and_emtp()
            self._update_status(workspace, "emtp_closed")

            removed_files = self._cleanup_run_workspace(workspace)
            self._update_status(
                workspace,
                "completed",
                removed_files=removed_files,
            )
            LOGGER.info("%s: removed %d non-retained files.", run_label, removed_files)

        except Exception as error:
            try:
                self._close_design_and_emtp()
            except Exception:
                pass
            if workspace is not None:
                self._update_status(
                    workspace,
                    "failed",
                    error=f"{type(error).__name__}: {error}",
                )
            LOGGER.exception(
                "%s: failed after %.1f s: %s: %s",
                run_label,
                perf_counter() - started_timer,
                type(error).__name__,
                error,
            )
            self._close_run_logging()
            return WorkerResult(
                execution_id=execution_id,
                study_id=worker_input.study_id,
                run_id=worker_input.run_id,
                state="failed",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
                artifacts=self._artifacts(workspace),
                error=f"{type(error).__name__}: {error}",
            )

        LOGGER.info(
            "%s: completed in %.1f s.", run_label, perf_counter() - started_timer
        )
        result = WorkerResult(
            execution_id=execution_id,
            study_id=worker_input.study_id,
            run_id=worker_input.run_id,
            state="completed",
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
            artifacts=self._artifacts(workspace),
        )
        self._close_run_logging()
        return result

    def _preparing_workspace(self, worker_input: WorkerInput) -> PreparedRunWorkspace:
        """Create the run folder and its initial files before EMTP is opened."""
        return RunWorkspace(worker_input).prepare()

    def _start_emtp(self) -> None:
        """Start or attach to the EMTP instance assigned to this worker."""
        self._emtp_client = EmtpComClient()
        self._emtp_object = self._emtp_client.emtp_object

    def _open_design(self, workspace: PreparedRunWorkspace) -> None:
        """Open the copied ECF model from the prepared run workspace."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        Design.open_design(self._emtp_object, str(workspace.model_path))
        self._design_is_open = True

    def _apply_parameters(self, worker_input: WorkerInput) -> PlantSetterReport:
        """Give the run parameters to PlantSetter and apply them to the design."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        return PlantSetter(self._emtp_object).apply(worker_input)

    def _save_design_after_parameterization(self) -> None:
        """Save the design after PlantSetter finishes."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        Design.save(self._emtp_object)

    def _run_load_flow(self) -> None:
        """Run the EMTP load-flow calculation for this run."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        Simulation.run_load_flow(self._emtp_object)

    def _run_time_domain_simulation(self, worker_input: WorkerInput) -> None:
        """Run the EMTP time-domain simulation for this run."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        tmax = float(worker_input.simulation.get("tmax", 10.0))
        if tmax <= 0:
            raise ValueError("simulation.tmax must be greater than zero.")
        Simulation.run_time_domain(self._emtp_object, tmax=tmax)

    def _save_design_after_simulation(self) -> None:
        """Save the final design state and simulation artifacts."""
        if self._emtp_object is None:
            raise RuntimeError("EMTP has not been started.")
        Design.save(self._emtp_object)

    def _close_design_and_emtp(self) -> None:
        """Close the design and the EMTP instance used by this worker."""
        close_error: Exception | None = None
        try:
            if self._emtp_object is not None and self._design_is_open:
                Design.close_design(self._emtp_object)
        except Exception as error:
            close_error = error
        finally:
            self._design_is_open = False
            if self._emtp_client is not None:
                self._emtp_client.disconnect()
            self._emtp_client = None
            self._emtp_object = None

        if close_error is not None:
            raise close_error

    def _configure_run_logging(self, workspace: PreparedRunWorkspace) -> None:
        """Write this worker's lifecycle events to its own run folder."""
        self._close_run_logging()
        handler = logging.FileHandler(
            workspace.directory / "worker.log",
            encoding="utf-8",
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        LOGGER.setLevel(logging.INFO)
        LOGGER.addHandler(handler)
        self._run_log_handler = handler

    def _close_run_logging(self) -> None:
        """Release the file handler before another run can start."""
        if self._run_log_handler is None:
            return
        LOGGER.removeHandler(self._run_log_handler)
        self._run_log_handler.close()
        self._run_log_handler = None

    @staticmethod
    def _artifacts(workspace: PreparedRunWorkspace | None) -> dict[str, str]:
        if workspace is None:
            return {}
        return {
            "directory": str(workspace.directory),
            "run_input": str(workspace.run_json_path),
            "parameters": str(workspace.parameters_csv_path),
            "status": str(workspace.status_path),
            "log": str(workspace.directory / "worker.log"),
        }

    @staticmethod
    def _cleanup_run_workspace(workspace: PreparedRunWorkspace) -> int:
        """Keep selected outputs and remove every other file from a completed run."""
        retained_extensions = {".mda", ".m", ".net", ".csv", ".json", ".log"}
        removed_count = 0
        for path in workspace.directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in retained_extensions:
                continue
            path.unlink()
            removed_count += 1
        return removed_count

    @staticmethod
    def _update_status(
        workspace: PreparedRunWorkspace,
        state: str,
        *,
        error: str | None = None,
        parameterized_devices: int | None = None,
        removed_files: int | None = None,
    ) -> None:
        """Persist the current worker state for the orchestrator and GUI."""
        previous_data: dict[str, object] = {}
        if workspace.status_path.exists():
            with workspace.status_path.open("r", encoding="utf-8") as stream:
                previous_data = json.load(stream)

        data = {
            "study_id": workspace.worker_input.study_id,
            "run_id": workspace.worker_input.run_id,
            "state": state,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if "parameterized_devices" in previous_data:
            data["parameterized_devices"] = previous_data["parameterized_devices"]
        if "removed_files" in previous_data:
            data["removed_files"] = previous_data["removed_files"]
        if error is not None:
            data["error"] = error
        if parameterized_devices is not None:
            data["parameterized_devices"] = parameterized_devices
        if removed_files is not None:
            data["removed_files"] = removed_files

        temporary_path = workspace.status_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_path, workspace.status_path)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Prepared study selected for this local proof of concept.
    study_directory = Path(r"C:\MonteCarlo Cases\20260928_1552_644292")
    run_id = 3
    tmax = 10.0

    # 2. The worker order has only the three values an orchestrator provides.
    worker_input = WorkerInput(
        study_directory=study_directory,
        run_id=run_id,
        tmax=tmax,
    )

    # print(worker_input)

    # 3. Create the worker for this one run.
    worker = RunWorker()

    # 4. Execute its complete lifecycle.
    result = worker.execute(worker_input)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    raise SystemExit(0 if result.succeeded else 1)
