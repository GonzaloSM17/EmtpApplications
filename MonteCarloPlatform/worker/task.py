"""Resolve and validate the minimal order received by one worker."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

WORKER_INPUT_SCHEMA_VERSION = 3
STUDY_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class UnitParameters:
    """The resolved data used to parameterize one plant in a worker run."""

    unit_id: str
    unit_path: str
    generator_name: str
    generator_type: str
    zone: str
    in_service: int
    parameters: dict[str, float] = field(default_factory=dict)
    design_variables: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id cannot be empty.")
        if not self.unit_path:
            raise ValueError("unit_path cannot be empty.")
        if not self.generator_name:
            raise ValueError("generator_name cannot be empty.")
        if not self.generator_type:
            raise ValueError("generator_type cannot be empty.")
        if not self.zone:
            raise ValueError("zone cannot be empty.")
        if self.in_service not in (0, 1):
            raise ValueError("in_service must be 0 or 1.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnitParameters:
        return cls(
            unit_id=str(data["unit_id"]),
            unit_path=str(data["unit_path"]),
            generator_name=str(data["generator_name"]),
            generator_type=str(data["generator_type"]),
            zone=str(data["zone"]),
            in_service=int(data["in_service"]),
            parameters={
                str(name): float(value)
                for name, value in dict(data.get("parameters", {})).items()
            },
            design_variables={
                str(name): float(value)
                for name, value in dict(data.get("design_variables", {})).items()
                if value is not None
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_path": self.unit_path,
            "generator_name": self.generator_name,
            "generator_type": self.generator_type,
            "zone": self.zone,
            "in_service": self.in_service,
            "parameters": self.parameters,
            "design_variables": self.design_variables,
        }


@dataclass(frozen=True, slots=True)
class WorkerInput:
    """One minimal worker order plus its validated, resolved study data.

    The orchestrator provides only ``study_directory``, ``run_id`` and
    ``tmax``. This object resolves the manifest and parameter block into the
    read-only properties consumed by ``RunWorker``.
    """

    study_directory: Path
    run_id: int
    tmax: float
    _study_id: str = field(init=False, repr=False)
    _source_model_path: Path = field(init=False, repr=False)
    _run_directory: Path = field(init=False, repr=False)
    _parameter_block_path: Path = field(init=False, repr=False)
    _units: tuple[UnitParameters, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        study_directory = Path(self.study_directory).resolve()
        if not study_directory.is_dir():
            raise NotADirectoryError(f"Study directory not found: {study_directory}")
        if not isinstance(self.run_id, int) or isinstance(self.run_id, bool):
            raise TypeError("run_id must be an integer.")
        if self.run_id <= 0:
            raise ValueError("run_id must be greater than zero.")

        try:
            tmax = float(self.tmax)
        except (TypeError, ValueError) as error:
            raise TypeError("tmax must be numeric.") from error
        if tmax <= 0:
            raise ValueError("tmax must be greater than zero.")

        manifest_path = study_directory / "manifest.json"
        manifest = self._read_json(manifest_path, "Study manifest")
        if int(manifest.get("schema_version", 0)) != STUDY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported study schema version in {manifest_path.name}."
            )

        study_id = str(manifest.get("study_id", "")).strip()
        if not study_id:
            raise ValueError("Study manifest does not define study_id.")

        source_model_path = self._resolve_model_path(study_directory, manifest)
        run_root = self._resolve_run_root(study_directory, manifest)
        run_directory = run_root / f"run_{self.run_id:06d}"
        if run_directory.exists():
            raise FileExistsError(f"Run directory already exists: {run_directory}")

        parameter_block_path, run_data = self._resolve_run_data(
            study_directory=study_directory,
            study_id=study_id,
            manifest=manifest,
        )
        units = self._resolve_units(manifest, run_data)
        run_root.mkdir(parents=True, exist_ok=True)

        object.__setattr__(self, "study_directory", study_directory)
        object.__setattr__(self, "tmax", tmax)
        object.__setattr__(self, "_study_id", study_id)
        object.__setattr__(self, "_source_model_path", source_model_path)
        object.__setattr__(self, "_run_directory", run_directory)
        object.__setattr__(self, "_parameter_block_path", parameter_block_path)
        object.__setattr__(self, "_units", units)

    @property
    def study_id(self) -> str:
        return self._study_id

    @property
    def run_name(self) -> str:
        return f"run_{self.run_id:06d}"

    @property
    def source_model_path(self) -> Path:
        return self._source_model_path

    @property
    def run_directory(self) -> Path:
        return self._run_directory

    @property
    def parameter_block_path(self) -> Path:
        return self._parameter_block_path

    @property
    def units(self) -> tuple[UnitParameters, ...]:
        return self._units

    @property
    def simulation(self) -> dict[str, float]:
        return {"tmax": self.tmax}

    @classmethod
    def from_json(cls, path: str | Path) -> WorkerInput:
        """Rebuild a worker order from its retained ``run.json`` request."""
        input_path = Path(path).resolve()
        data = cls._read_json(input_path, "Worker input")
        if int(data.get("schema_version", 0)) != WORKER_INPUT_SCHEMA_VERSION:
            raise ValueError("Unsupported worker input schema version.")
        request = data.get("request")
        if not isinstance(request, Mapping):
            raise ValueError("Worker input does not contain a request.")
        return cls(
            study_directory=Path(request["study_directory"]),
            run_id=int(request["run_id"]),
            tmax=float(request["tmax"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Retain the minimal order and its resolved execution snapshot."""
        return {
            "schema_version": WORKER_INPUT_SCHEMA_VERSION,
            "request": {
                "study_directory": str(self.study_directory),
                "run_id": self.run_id,
                "tmax": self.tmax,
            },
            "resolved": {
                "study_id": self.study_id,
                "source_model_path": str(self.source_model_path),
                "run_directory": str(self.run_directory),
                "parameter_block_path": str(self.parameter_block_path),
                "units": [unit.to_dict() for unit in self.units],
                "simulation": self.simulation,
            },
        }

    def _resolve_run_data(
        self,
        *,
        study_directory: Path,
        study_id: str,
        manifest: Mapping[str, Any],
    ) -> tuple[Path, Mapping[str, Any]]:
        parameter_entries = manifest.get("parameter_files")
        if not isinstance(parameter_entries, list):
            raise ValueError("Study manifest does not define parameter_files.")

        matching_entry = next(
            (
                entry
                for entry in parameter_entries
                if isinstance(entry, Mapping)
                and int(entry["first_run"]) <= self.run_id <= int(entry["last_run"])
            ),
            None,
        )
        if matching_entry is None:
            raise KeyError(f"Run {self.run_id} is not indexed by the study manifest.")

        block_name = matching_entry.get("json_file") or matching_entry.get("file")
        if not isinstance(block_name, str) or not block_name:
            raise ValueError("Parameter block entry does not define a JSON file.")
        parameter_block_path = self._resolve_study_file(
            study_directory,
            block_name,
            "Parameter block",
        )
        parameter_block = self._read_json(parameter_block_path, "Parameter block")
        if int(parameter_block.get("schema_version", 0)) != STUDY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported parameter block schema in {parameter_block_path.name}."
            )
        if str(parameter_block.get("study_id", "")) != study_id:
            raise ValueError(
                f"Parameter block '{parameter_block_path.name}' belongs to another study."
            )

        runs = parameter_block.get("runs")
        if not isinstance(runs, list):
            raise ValueError(
                f"Parameter block '{parameter_block_path.name}' has no runs."
            )
        run_data = next(
            (
                item
                for item in runs
                if isinstance(item, Mapping) and int(item["run_id"]) == self.run_id
            ),
            None,
        )
        if run_data is None:
            raise KeyError(
                f"Run {self.run_id} is missing from '{parameter_block_path.name}'."
            )
        return parameter_block_path, run_data

    @staticmethod
    def _resolve_units(
        manifest: Mapping[str, Any],
        run_data: Mapping[str, Any],
    ) -> tuple[UnitParameters, ...]:
        inventory = manifest.get("units")
        if not isinstance(inventory, list) or not inventory:
            raise ValueError("Study manifest does not define a unit inventory.")

        units_by_id: dict[str, Mapping[str, Any]] = {}
        for unit in inventory:
            if not isinstance(unit, Mapping):
                raise ValueError("Study inventory contains an invalid unit entry.")
            unit_id = str(unit.get("unit_id", ""))
            if not unit_id or unit_id in units_by_id:
                raise ValueError(
                    "Study inventory contains duplicate or empty unit_id values."
                )
            units_by_id[unit_id] = unit

        run_units = run_data.get("units")
        if not isinstance(run_units, list) or not run_units:
            raise ValueError("Run does not define parameter units.")

        resolved_units: list[UnitParameters] = []
        seen_unit_ids: set[str] = set()
        for run_unit in run_units:
            if not isinstance(run_unit, Mapping):
                raise ValueError("Run contains an invalid unit entry.")
            unit_id = str(run_unit.get("unit_id", ""))
            if unit_id in seen_unit_ids:
                raise ValueError(f"Run contains duplicate unit_id '{unit_id}'.")
            try:
                unit_metadata = units_by_id[unit_id]
            except KeyError as error:
                raise KeyError(f"Run references unknown unit '{unit_id}'.") from error
            seen_unit_ids.add(unit_id)
            resolved_units.append(
                UnitParameters.from_dict({**unit_metadata, **run_unit})
            )

        return tuple(resolved_units)

    @staticmethod
    def _resolve_model_path(
        study_directory: Path,
        manifest: Mapping[str, Any],
    ) -> Path:
        model = manifest.get("model")
        if not isinstance(model, Mapping):
            raise ValueError("Study manifest does not define model metadata.")
        model_name = model.get("file")
        if not isinstance(model_name, str) or not model_name:
            raise ValueError("Study manifest does not define the model file.")
        model_path = WorkerInput._resolve_study_file(
            study_directory,
            model_name,
            "Base model",
        )
        if model_path.suffix.lower() != ".ecf":
            raise ValueError(f"Base model must have .ecf extension: {model_path.name}")
        return model_path

    @staticmethod
    def _resolve_run_root(
        study_directory: Path,
        manifest: Mapping[str, Any],
    ) -> Path:
        run_directory_name = manifest.get("run_directory", "runs")
        if not isinstance(run_directory_name, str) or not run_directory_name:
            raise ValueError("Study manifest has an invalid run_directory value.")
        run_root = (study_directory / run_directory_name).resolve()
        if not run_root.is_relative_to(study_directory):
            raise ValueError("run_directory must remain inside the study directory.")
        if run_root.exists() and not run_root.is_dir():
            raise NotADirectoryError(f"Run root is not a directory: {run_root}")
        return run_root

    @staticmethod
    def _resolve_study_file(
        study_directory: Path,
        relative_path: str,
        label: str,
    ) -> Path:
        path = (study_directory / relative_path).resolve()
        if not path.is_relative_to(study_directory):
            raise ValueError(f"{label} must remain inside the study directory.")
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
        return path

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
        try:
            with path.open("r", encoding="utf-8-sig") as stream:
                data = json.load(stream)
        except json.JSONDecodeError as error:
            raise ValueError(f"{label} is not valid JSON: {path}") from error
        if not isinstance(data, dict):
            raise ValueError(f"{label} must contain a JSON object: {path}")
        return data
