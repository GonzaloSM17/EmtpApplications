"""Build the durable input folder consumed later by the Monte Carlo orchestrator.

This module creates a study once.  It does not create a run folder, modify a
model for a run, or start a simulation; those are responsibilities of the
future orchestrator and worker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import csv
import json
import logging
from pathlib import Path
from random import Random
from secrets import randbits, token_hex
from shutil import copy2
from time import perf_counter
from typing import Any, Iterator
import os

import tkinter as tk
from tkinter import filedialog

from emtp_utils import Design
from parametric_calculating import (
    ParameterConfig,
    ParameterGenerator,
    ParameterRange,
)
from parametric_selecting import (
    GeneratorParameterRecord,
    ParameterAssignment,
    ParameterRun,
)

DEFAULT_OUTPUT_ROOT = Path(r"C:\MonteCarlo Cases")
SCHEMA_VERSION = 1
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedStudy:
    """Locations and identifiers created by :class:`StudyBuilder`."""

    study_id: str
    study_directory: Path
    manifest_path: Path
    base_model_path: Path
    parameter_files: tuple[Path, ...]
    parameter_csv_files: tuple[Path, ...]


class StudyBuilder:
    """Create a study folder and its parameter files.

    ``emtp_object`` is optional. When omitted, EMTP starts only after the
    study directory and its ``base.ecf`` copy have been created.
    """

    def __init__(
        self,
        *,
        emtp_object: Any | None = None,
        parameter_generator: ParameterGenerator,
        number_of_runs: int,
        ecf_path: str | Path | None = None,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        block_size: int = 1_000,
        seed: int | None = None,
    ) -> None:
        if number_of_runs <= 0:
            raise ValueError("number_of_runs must be greater than zero.")
        if block_size <= 0:
            raise ValueError("block_size must be greater than zero.")

        self.emtp_object = emtp_object
        self._emtp_client: Any | None = None
        self.parameter_generator = parameter_generator
        self.number_of_runs = number_of_runs
        self.ecf_path = Path(ecf_path) if ecf_path is not None else None
        self.output_root = Path(output_root)
        self.block_size = block_size
        self.seed = seed if seed is not None else randbits(64)

    def prepare(self) -> PreparedStudy:
        """Create a complete, validated study folder.

        ``manifest.json`` is written last.  Its presence signals that the
        future orchestrator may consume the study.
        """
        source_model_path = self._resolve_ecf_path()
        study_id, study_directory = self._create_study_directory()
        base_model_path = study_directory / "base.ecf"
        LOGGER.info("Study %s: copying base model.", study_id)
        copy2(source_model_path, base_model_path)
        (study_directory / "runs").mkdir()

        try:
            self._open_copied_model(base_model_path)
            assignment = ParameterAssignment(
                emtp_object=self.emtp_object,
                parameter_generator=self.parameter_generator,
                number_of_runs=self.number_of_runs,
                name=study_id,
            )
            self.parameter_generator.rng = Random(self.seed)
            LOGGER.info("Inspecting units and generating parameters.")

            parameter_files, inventory = self._write_parameter_blocks(
                study_directory=study_directory,
                runs=assignment.iter_runs(),
                study_id=study_id,
            )
            manifest_path = study_directory / "manifest.json"
            manifest = self._build_manifest(
                study_id=study_id,
                source_model_path=source_model_path,
                base_model_path=base_model_path,
                inventory=inventory,
                parameter_files=parameter_files,
            )
            self._write_json_atomically(manifest_path, manifest)
            LOGGER.info("Study ready: %s", study_directory)

            return PreparedStudy(
                study_id=study_id,
                study_directory=study_directory,
                manifest_path=manifest_path,
                base_model_path=base_model_path,
                parameter_files=tuple(parameter_files),
                parameter_csv_files=tuple(
                    path.with_suffix(".csv") for path in parameter_files
                ),
            )
        finally:
            self._close_owned_emtp()

    def _resolve_ecf_path(self) -> Path:
        path = self.ecf_path or self._select_ecf_path()
        if path is None:
            raise RuntimeError("No ECF model was selected.")
        if not path.is_file():
            raise FileNotFoundError(f"ECF model not found: {path}")
        if path.suffix.lower() != ".ecf":
            raise ValueError(f"Expected an .ecf model, received: {path.name}")
        return path.resolve()

    @staticmethod
    def _select_ecf_path() -> Path | None:

        root = tk.Tk()
        root.withdraw()
        try:
            selected_path = filedialog.askopenfilename(
                title="Seleccionar diseño EMTP",
                filetypes=[("EMTP Design", "*.ecf")],
            )
        finally:
            root.destroy()

        return Path(selected_path) if selected_path else None

    def _create_study_directory(self) -> tuple[str, Path]:
        self.output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        for _ in range(20):
            study_id = f"{timestamp}_{token_hex(3)}"
            study_directory = self.output_root / study_id
            try:
                study_directory.mkdir()
            except FileExistsError:
                continue
            return study_id, study_directory

        raise RuntimeError("Could not generate a unique study directory name.")

    def _open_copied_model(self, base_model_path: Path) -> None:
        if self.emtp_object is None:
            from com_client import EmtpComClient

            LOGGER.info("Starting EMTP.")
            self._emtp_client = EmtpComClient()
            self.emtp_object = self._emtp_client.emtp_object
        LOGGER.info("Opening base.ecf in EMTP.")
        Design.open_design(self.emtp_object, str(base_model_path))
        LOGGER.info("Base design opened.")

    def _close_owned_emtp(self) -> None:
        """Close only the EMTP instance that this builder started itself."""
        if self._emtp_client is None:
            return

        try:
            if self.emtp_object is not None:
                try:
                    Design.close_design(self.emtp_object)
                except Exception:
                    # EMTP may not have completed opening the design after a
                    # failure. The application still needs to be released.
                    pass
        finally:
            self._emtp_client.disconnect()
            self._emtp_client = None
            self.emtp_object = None

    def _write_parameter_blocks(
        self,
        *,
        study_directory: Path,
        runs: Iterator[ParameterRun],
        study_id: str,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        parameter_files: list[Path] = []
        inventory: list[dict[str, Any]] | None = None
        block: list[ParameterRun] = []
        block_number = 0
        total_blocks = (self.number_of_runs + self.block_size - 1) // self.block_size

        for run in runs:
            if not block:
                block_number += 1
                last_run = min(
                    run.run_id + self.block_size - 1,
                    self.number_of_runs,
                )
                LOGGER.info(
                    "Block %s/%s: runs %06d to %06d.",
                    block_number,
                    total_blocks,
                    run.run_id,
                    last_run,
                )
            block.append(run)
            if len(block) == self.block_size:
                path, current_inventory = self._write_parameter_block(
                    study_directory=study_directory,
                    study_id=study_id,
                    runs=block,
                )
                parameter_files.append(path)
                inventory = inventory or current_inventory
                block = []

        if block:
            path, current_inventory = self._write_parameter_block(
                study_directory=study_directory,
                study_id=study_id,
                runs=block,
            )
            parameter_files.append(path)
            inventory = inventory or current_inventory

        if inventory is None:
            raise RuntimeError("No parameter runs were generated.")
        return parameter_files, inventory

    def _write_parameter_block(
        self,
        *,
        study_directory: Path,
        study_id: str,
        runs: list[ParameterRun],
    ) -> tuple[Path, list[dict[str, Any]]]:
        first_run = runs[0].run_id
        last_run = runs[-1].run_id
        path = study_directory / f"parameters_{first_run:06d}_{last_run:06d}.json"
        started_at = perf_counter()
        serialized_runs = [self._serialize_run(run) for run in runs]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "first_run": first_run,
            "last_run": last_run,
            "runs": serialized_runs,
        }
        self._write_json_atomically(path, payload)
        json_elapsed = perf_counter() - started_at
        LOGGER.info(
            "Block %06d-%06d: JSON written in %.1f s.",
            first_run,
            last_run,
            json_elapsed,
        )
        self._write_csv_atomically(
            path.with_suffix(".csv"),
            runs=runs,
        )
        LOGGER.info(
            "Block %06d-%06d: CSV written in %.1f s.",
            first_run,
            last_run,
            perf_counter() - started_at - json_elapsed,
        )

        inventory = [self._inventory_entry(record) for record in runs[0].records]
        return path, inventory

    def _build_manifest(
        self,
        *,
        study_id: str,
        source_model_path: Path,
        base_model_path: Path,
        inventory: list[dict[str, Any]],
        parameter_files: list[Path],
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "study_id": study_id,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": {
                "file": base_model_path.name,
                "original_name": source_model_path.name,
                "sha256": self._sha256(base_model_path),
            },
            "generation": {
                "run_count": self.number_of_runs,
                "block_size": self.block_size,
                "seed": self.seed,
                "config": asdict(self.parameter_generator.config),
            },
            "units": inventory,
            "run_directory": "runs",
            "parameter_files": [
                {
                    "json_file": path.name,
                    "csv_file": path.with_suffix(".csv").name,
                    "first_run": int(path.stem.split("_")[1]),
                    "last_run": int(path.stem.split("_")[2]),
                }
                for path in parameter_files
            ],
        }

    @staticmethod
    def _serialize_run(run: ParameterRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "units": [StudyBuilder._serialize_record(record) for record in run.records],
        }

    @staticmethod
    def _serialize_record(record: GeneratorParameterRecord) -> dict[str, Any]:
        return {
            "unit_path": record.unit_path,
            "generator_name": record.generator_name,
            "generator_type": record.generator_type,
            "in_service": record.in_service,
            "parameters": record.parameters,
            "design_variables": {
                "damping_ratio": record.damping_ratio,
                "bandwidth_hz": record.bandwidth_hz,
                "natural_frequency_rad_s": record.natural_frequency_rad_s,
            },
        }

    @staticmethod
    def _inventory_entry(record: GeneratorParameterRecord) -> dict[str, Any]:
        return {
            "unit_path": record.unit_path,
            "generator_name": record.generator_name,
            "generator_type": record.generator_type,
        }

    @staticmethod
    def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary_path, path)

    @staticmethod
    def _write_csv_atomically(
        path: Path,
        *,
        runs: list[ParameterRun],
    ) -> None:
        """Write a spreadsheet-friendly view of the same parameter records.

        Semicolons and UTF-8 with BOM make the file open correctly in the
        usual regional configuration of Microsoft Excel.
        """
        headers = (
            "RunId",
            "UnitPath",
            "GeneratorName",
            "GeneratorType",
            "InService",
            "Kp",
            "Ki",
            "Kqv",
            "Rrpw",
            "DampingRatio",
            "BandwidthHz",
            "NaturalFrequencyRadS",
        )
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers, delimiter=";")
            writer.writeheader()
            for run in runs:
                for record in run.records:
                    writer.writerow(
                        {
                            "RunId": run.run_id,
                            "UnitPath": record.unit_path,
                            "GeneratorName": record.generator_name,
                            "GeneratorType": record.generator_type,
                            "InService": record.in_service,
                            "Kp": record.kp,
                            "Ki": record.ki,
                            "Kqv": record.kqv,
                            "Rrpw": record.rrpw,
                            "DampingRatio": record.damping_ratio,
                            "BandwidthHz": record.bandwidth_hz,
                            "NaturalFrequencyRadS": record.natural_frequency_rad_s,
                        }
                    )
        os.replace(temporary_path, path)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parameter_config = ParameterConfig(
        damping_ratio_range=ParameterRange(minimum=0.6, maximum=1.0),
        bandwidth_range=ParameterRange(minimum=2.5, maximum=15.0),
        # kqv_range=ParameterRange(minimum=1.0, maximum=2.0),
        # rrpw_range=ParameterRange(minimum=0.5, maximum=1.0),
    )

    # The ECF selector opens because ecf_path is omitted here.  A script or a
    # future GUI can pass it directly instead.
    builder = StudyBuilder(
        parameter_generator=ParameterGenerator(parameter_config),
        number_of_runs=1000,
    )

    prepared_study = builder.prepare()

    print(f"Study ID: {prepared_study.study_id}")
    print(f"Directory: {prepared_study.study_directory}")
    print(f"Manifest: {prepared_study.manifest_path}")
    print(f"JSON parameter files: {len(prepared_study.parameter_files)}")
    print(f"CSV parameter files: {len(prepared_study.parameter_csv_files)}")
