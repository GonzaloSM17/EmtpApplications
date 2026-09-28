"""The one-run worker lifecycle.

The worker receives one self-contained ``WorkerInput``. Only workspace
preparation is active at this stage; EMTP operations follow in later stages.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

from com_client import EmtpComClient
from emtp_utils import Design, Simulation
from MonteCarloPlatform.worker.plant_setter import PlantSetter, PlantSetterReport
from MonteCarloPlatform.worker.result import WorkerResult
from MonteCarloPlatform.worker.task import UnitParameters, WorkerInput
from MonteCarloPlatform.worker.workspace import PreparedRunWorkspace, RunWorkspace


class RunWorker:
    """Execute the currently implemented stages for one run task."""

    def __init__(self) -> None:
        self._emtp_client: EmtpComClient | None = None
        self._emtp_object = None
        self._design_is_open = False

    def execute(self, worker_input: WorkerInput) -> WorkerResult:
        started_at = datetime.now().astimezone()
        execution_id = f"{worker_input.study_id}_{worker_input.run_name}"
        workspace: PreparedRunWorkspace | None = None

        try:
            workspace = self._preparing_workspace(worker_input)
            self._update_status(workspace, "workspace_ready")

            self._start_emtp()
            self._update_status(workspace, "emtp_started")

            self._open_design(workspace)
            self._update_status(workspace, "design_opened")

            report = self._apply_parameters(worker_input)
            self._update_status(
                workspace,
                "parameters_applied",
                parameterized_devices=len(report.changes),
            )

            self._save_design_after_parameterization()
            self._update_status(workspace, "saved_before_simulation")

            self._run_load_flow()
            self._update_status(workspace, "load_flow_completed")

            self._run_time_domain_simulation(worker_input)
            self._update_status(workspace, "time_domain_completed")

            self._save_design_after_simulation()
            self._update_status(workspace, "saved_after_simulation")

            self._close_design_and_emtp()
            self._update_status(workspace, "emtp_closed")

            self._cleanup_run_workspace(workspace)
            self._update_status(workspace, "completed")

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
            return WorkerResult(
                execution_id=execution_id,
                study_id=worker_input.study_id,
                run_id=worker_input.run_id,
                state="failed",
                started_at=started_at,
                finished_at=datetime.now().astimezone(),
                artifacts={},
                error=f"{type(error).__name__}: {error}",
            )

        return WorkerResult(
            execution_id=execution_id,
            study_id=worker_input.study_id,
            run_id=worker_input.run_id,
            state="completed",
            started_at=started_at,
            finished_at=datetime.now().astimezone(),
            artifacts={
                "directory": str(workspace.directory),
                "run_input": str(workspace.run_json_path),
                "parameters": str(workspace.parameters_csv_path),
                "status": str(workspace.status_path),
            },
        )

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

    def _cleanup_run_workspace(self, workspace: PreparedRunWorkspace) -> None:
        """Remove run artifacts that are not required after simulation."""
        workspace.model_path.unlink(missing_ok=True)

    @staticmethod
    def _update_status(
        workspace: PreparedRunWorkspace,
        state: str,
        *,
        error: str | None = None,
        parameterized_devices: int | None = None,
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
        if error is not None:
            data["error"] = error
        if parameterized_devices is not None:
            data["parameterized_devices"] = parameterized_devices

        temporary_path = workspace.status_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_path, workspace.status_path)


if __name__ == "__main__":

    # 1. Prepared study selected for this local proof of concept.
    study_directory = Path(r"C:\MonteCarlo Cases\20260924_1708_f086d6")
    run_id = 1
    tmax = 10.0

    # 2. Build the WorkerInput that an orchestrator will later send.
    manifest_path = study_directory / "manifest.json"

    with manifest_path.open("r", encoding="utf-8-sig") as stream:
        manifest = json.load(stream)

    parameter_file = None
    for entry in manifest.get("parameter_files", []):
        if int(entry["first_run"]) <= run_id <= int(entry["last_run"]):
            parameter_file = entry.get("json_file") or entry.get("file")
            break

    if parameter_file is None:
        raise KeyError(f"Run {run_id} is not indexed by the study manifest.")

    parameter_path = study_directory / parameter_file
    with parameter_path.open("r", encoding="utf-8-sig") as stream:
        parameter_block = json.load(stream)

    run_data = next(
        (
            item
            for item in parameter_block.get("runs", [])
            if int(item["run_id"]) == run_id
        ),
        None,
    )
    if run_data is None:
        raise RuntimeError(
            f"Run {run_id} is indexed by '{parameter_path.name}' but is missing from it."
        )

    worker_input = WorkerInput(
        study_id=str(manifest["study_id"]),
        run_id=run_id,
        source_model_path=(study_directory / manifest["model"]["file"]).resolve(),
        run_directory=study_directory / "runs" / f"run_{run_id:06d}",
        units=tuple(UnitParameters.from_dict(item) for item in run_data["units"]),
        simulation={**manifest.get("simulation", {}), "tmax": tmax},
    )

    # print(worker_input)

    # 3. Create the worker for this one run.
    worker = RunWorker()

    # 4. Execute its complete lifecycle.
    result = worker.execute(worker_input)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    raise SystemExit(0 if result.succeeded else 1)
