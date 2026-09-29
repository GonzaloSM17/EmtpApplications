"""Creation of the self-contained folder consumed by one worker."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from secrets import token_hex
from shutil import copy2, rmtree
from typing import Any

from MonteCarloPlatform.worker.task import WorkerInput


@dataclass(frozen=True, slots=True)
class PreparedRunWorkspace:

    worker_input: WorkerInput
    directory: Path
    model_path: Path
    run_json_path: Path
    parameters_csv_path: Path
    status_path: Path


class RunWorkspace:
    """Create one run folder without opening EMTP."""

    def __init__(self, worker_input: WorkerInput) -> None:
        self.worker_input = worker_input

    def prepare(self) -> PreparedRunWorkspace:
        source_model_path = self.worker_input.source_model_path
        if not source_model_path.is_file():
            raise FileNotFoundError(f"Base model not found: {source_model_path}")

        final_directory = self.worker_input.run_directory
        self._reset_run_directory(final_directory)
        final_directory.parent.mkdir(parents=True, exist_ok=True)

        temporary_directory = final_directory.parent / (
            f".{self.worker_input.run_name}_{token_hex(3)}.tmp"
        )
        temporary_directory.mkdir()

        model_path = temporary_directory / source_model_path.name
        run_json_path = temporary_directory / "run.json"
        parameters_csv_path = temporary_directory / "parameters.csv"
        status_path = temporary_directory / "status.json"

        try:
            copy2(source_model_path, model_path)
            self._write_json_atomically(run_json_path, self.worker_input.to_dict())
            self._write_parameters_csv(parameters_csv_path)
            self._write_json_atomically(
                status_path,
                {
                    "study_id": self.worker_input.study_id,
                    "run_id": self.worker_input.run_id,
                    "state": "workspace_ready",
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                },
            )
            os.replace(temporary_directory, final_directory)
        except Exception:
            if temporary_directory.exists():
                rmtree(temporary_directory)
            raise

        return PreparedRunWorkspace(
            worker_input=self.worker_input,
            directory=final_directory,
            model_path=final_directory / model_path.name,
            run_json_path=final_directory / run_json_path.name,
            parameters_csv_path=final_directory / parameters_csv_path.name,
            status_path=final_directory / status_path.name,
        )

    def _reset_run_directory(self, final_directory: Path) -> None:
        """Remove only this worker's previous run workspace before rebuilding it."""
        run_root = final_directory.parent.resolve()
        expected_directory = run_root / self.worker_input.run_name
        if final_directory != expected_directory:
            raise ValueError("Worker run directory does not match its run identifier.")
        if not run_root.is_relative_to(self.worker_input.study_directory):
            raise ValueError("Worker run directory must remain inside the study directory.")
        if not final_directory.exists() and not final_directory.is_symlink():
            return
        if final_directory.is_symlink():
            raise RuntimeError(f"Refusing to reset symbolic-link run directory: {final_directory}")
        if not final_directory.is_dir():
            raise NotADirectoryError(f"Run path is not a directory: {final_directory}")
        rmtree(final_directory)

    def _write_parameters_csv(self, path: Path) -> None:
        headers = (
            "RunId",
            "UnitId",
            "UnitPath",
            "GeneratorName",
            "GeneratorType",
            "Zone",
            "InService",
            "Kp",
            "Ki",
            "Kqv",
            "Rrpw",
            "DampingRatio",
            "BandwidthHz",
            "NaturalFrequencyRadS",
        )
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers, delimiter=";")
            writer.writeheader()
            for unit in self.worker_input.units:
                writer.writerow(
                    {
                        "RunId": self.worker_input.run_id,
                        "UnitId": unit.unit_id,
                        "UnitPath": unit.unit_path,
                        "GeneratorName": unit.generator_name,
                        "GeneratorType": unit.generator_type,
                        "Zone": unit.zone,
                        "InService": unit.in_service,
                        "Kp": unit.parameters.get("kp"),
                        "Ki": unit.parameters.get("ki"),
                        "Kqv": unit.parameters.get("kqv"),
                        "Rrpw": unit.parameters.get("rrpw"),
                        "DampingRatio": unit.design_variables.get("damping_ratio"),
                        "BandwidthHz": unit.design_variables.get("bandwidth_hz"),
                        "NaturalFrequencyRadS": unit.design_variables.get(
                            "natural_frequency_rad_s"
                        ),
                    }
                )

    @staticmethod
    def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary_path, path)
