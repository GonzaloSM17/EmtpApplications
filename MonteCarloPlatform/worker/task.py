"""The complete, self-contained input received by one worker."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

WORKER_INPUT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class UnitParameters:
    """The data used to parameterize one plant in a worker run."""

    unit_path: str
    generator_name: str
    generator_type: str
    in_service: int
    parameters: dict[str, float] = field(default_factory=dict)
    design_variables: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.unit_path:
            raise ValueError("unit_path cannot be empty.")
        if not self.generator_name:
            raise ValueError("generator_name cannot be empty.")
        if not self.generator_type:
            raise ValueError("generator_type cannot be empty.")
        if self.in_service not in (0, 1):
            raise ValueError("in_service must be 0 or 1.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnitParameters:
        return cls(
            unit_path=str(data["unit_path"]),
            generator_name=str(data["generator_name"]),
            generator_type=str(data["generator_type"]),
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
            "unit_path": self.unit_path,
            "generator_name": self.generator_name,
            "generator_type": self.generator_type,
            "in_service": self.in_service,
            "parameters": self.parameters,
            "design_variables": self.design_variables,
        }


@dataclass(frozen=True, slots=True)
class WorkerInput:
    """Everything required for a worker to start and execute one run.

    The orchestrator resolves the prepared study before creating this object.
    The worker never reads ``manifest.json`` or a parameter block.
    """

    study_id: str
    run_id: int
    source_model_path: Path
    run_directory: Path
    units: tuple[UnitParameters, ...]
    simulation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.study_id:
            raise ValueError("study_id cannot be empty.")
        if self.run_id <= 0:
            raise ValueError("run_id must be greater than zero.")
        if not self.source_model_path.is_absolute():
            raise ValueError("source_model_path must be absolute.")
        if not self.run_directory.is_absolute():
            raise ValueError("run_directory must be absolute.")
        if not self.units:
            raise ValueError("A run must contain at least one unit.")

    @property
    def run_name(self) -> str:
        return f"run_{self.run_id:06d}"

    @classmethod
    def from_json(cls, path: str | Path) -> WorkerInput:
        """Load the one-run input supplied to the worker."""
        input_path = Path(path).resolve()
        with input_path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)

        if (
            int(data.get("schema_version", WORKER_INPUT_SCHEMA_VERSION))
            != WORKER_INPUT_SCHEMA_VERSION
        ):
            raise ValueError("Unsupported worker run-input schema version.")

        return cls(
            study_id=str(data["study_id"]),
            run_id=int(data["run_id"]),
            source_model_path=Path(data["source_model_path"]),
            run_directory=Path(data["run_directory"]),
            units=tuple(UnitParameters.from_dict(item) for item in data["units"]),
            simulation=dict(data.get("simulation", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Portable JSON representation sent to and retained by the worker."""
        return {
            "schema_version": WORKER_INPUT_SCHEMA_VERSION,
            "study_id": self.study_id,
            "run_id": self.run_id,
            "source_model_path": str(self.source_model_path),
            "run_directory": str(self.run_directory),
            "units": [unit.to_dict() for unit in self.units],
            "simulation": self.simulation,
        }
