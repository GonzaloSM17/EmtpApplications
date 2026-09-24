from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from openpyxl import Workbook

from com_client import EmtpComClient
from parametric_calculating import (
    ParameterConfig,
    ParameterGenerator,
    ParameterRange,
    ParameterResult,
)
from unit_extractor import UnitExtractor

# =============================================================================
# Parameter data
# =============================================================================


@dataclass(frozen=True, slots=True)
class GeneratorParameterRecord:
    generator_name: str
    generator_type: str
    in_service: int
    unit_path: str | None = None

    # Parameters to be written in EMTP
    kp: float | None = None
    ki: float | None = None
    kqv: float | None = None
    rrpw: float | None = None

    # Design variables / traceability
    damping_ratio: float | None = None
    bandwidth_hz: float | None = None
    natural_frequency_rad_s: float | None = None

    @property
    def has_parameters(self) -> bool:
        return self.in_service == 1

    @property
    def parameters(self) -> dict[str, float]:
        """
        Parameters that a future setter must apply
        to the corresponding EMTP unit.
        """
        if not self.has_parameters:
            return {}

        values = {
            "kp": self.kp,
            "ki": self.ki,
            "kqv": self.kqv,
            "rrpw": self.rrpw,
        }

        return {
            parameter_name: value
            for parameter_name, value in values.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ParameterRun:
    run_id: int
    records: tuple[GeneratorParameterRecord, ...]

    def __iter__(self) -> Iterator[GeneratorParameterRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    @property
    def name(self) -> str:
        return f"Run_{self.run_id:06d}"

    @property
    def records_by_name(self) -> dict[str, GeneratorParameterRecord]:
        return {record.generator_name: record for record in self.records}

    def get_record(
        self,
        generator_name: str,
    ) -> GeneratorParameterRecord:
        try:
            return self.records_by_name[generator_name]

        except KeyError as error:
            raise KeyError(
                f"Generator '{generator_name}' " f"not found in {self.name}."
            ) from error


@dataclass(frozen=True, slots=True)
class ParameterTarget:
    """EMTP unit metadata shared by every run in a study."""

    generator_name: str
    generator_type: str
    unit_path: str
    in_service: int


# =============================================================================
# Parameter assignment
# =============================================================================


class ParameterAssignment:
    def __init__(
        self,
        emtp_object: Any,
        parameter_generator: ParameterGenerator,
        number_of_runs: int,
        name: str = "ParametricStudy",
    ) -> None:
        if number_of_runs <= 0:
            raise ValueError("number_of_runs must be greater than zero.")

        name = name.strip()

        if not name:
            raise ValueError("name cannot be empty.")

        self.emtp_object = emtp_object
        self.parameter_generator = parameter_generator
        self.number_of_runs = number_of_runs
        self.name = name

        self.runs: tuple[ParameterRun, ...] = ()

    def __iter__(self) -> Iterator[ParameterRun]:
        return iter(self.runs)

    def __len__(self) -> int:
        return len(self.runs)

    @property
    def is_executed(self) -> bool:
        return bool(self.runs)

    @property
    def number_of_units(self) -> int:
        return len(self.runs[0]) if self.runs else 0

    @property
    def number_of_records(self) -> int:
        return sum(len(run) for run in self.runs)

    def execute(self) -> ParameterAssignment:
        self.runs = tuple(self.iter_runs())

        return self

    def iter_runs(self) -> Iterator[ParameterRun]:
        """Yield parameter runs without retaining the whole study in memory.

        ``execute()`` remains available for the existing small-study workflow.
        Large studies should consume this iterator and persist runs in blocks.
        """
        targets = self._extract_targets()

        for run_id in range(1, self.number_of_runs + 1):
            yield self._generate_run(
                run_id=run_id,
                targets=targets,
            )

    def get_run(
        self,
        run_id: int,
    ) -> ParameterRun:
        self._require_execution()

        for run in self.runs:
            if run.run_id == run_id:
                return run

        raise KeyError(f"Run {run_id} not found in '{self.name}'.")

    def _require_execution(self) -> None:
        if not self.is_executed:
            raise RuntimeError(
                "ParameterAssignment has not been executed. "
                "Call execute() before accessing its runs."
            )

    def _generate_run(
        self,
        run_id: int,
        targets: tuple[ParameterTarget, ...],
    ) -> ParameterRun:
        return ParameterRun(
            run_id=run_id,
            records=tuple(
                self._generate_record(target=target)
                for target in targets
            ),
        )

    def _extract_targets(
        self,
    ) -> tuple[ParameterTarget, ...]:
        extractor = UnitExtractor(
            emtp_object=self.emtp_object,
        )

        extractor.execute()

        units = (
            [("PV", unit) for unit in extractor.units.pv_units]
            + [("WF", unit) for unit in extractor.units.wf_units]
            + [("BESS", unit) for unit in extractor.units.bess_units]
        )

        if not units:
            raise RuntimeError("No PV, WF or BESS units were found.")

        return tuple(
            self._build_target(
                generator_type=generator_type,
                unit=unit,
            )
            for generator_type, unit in units
        )

    @staticmethod
    def _build_target(
        generator_type: str,
        unit: Any,
    ) -> ParameterTarget:
        in_service = int(unit.get_in_service())

        generator_name = str(unit.object.name)
        unit_path = str(getattr(unit, "unit_path", generator_name))

        if in_service not in (0, 1):
            raise ValueError(
                f"Invalid in-service value for "
                f"'{generator_name}': "
                f"{in_service}."
            )

        return ParameterTarget(
            generator_name=generator_name,
            generator_type=generator_type,
            unit_path=unit_path,
            in_service=in_service,
        )

    def _generate_record(
        self,
        target: ParameterTarget,
    ) -> GeneratorParameterRecord:
        result = (
            self.parameter_generator.generate()
            if target.in_service == 1
            else None
        )

        return self._build_record(
            generator_name=target.generator_name,
            generator_type=target.generator_type,
            in_service=target.in_service,
            unit_path=target.unit_path,
            result=result,
        )

    @staticmethod
    def _build_record(
        generator_name: str,
        generator_type: str,
        in_service: int,
        unit_path: str,
        result: ParameterResult | None,
    ) -> GeneratorParameterRecord:
        if result is None:
            return GeneratorParameterRecord(
                generator_name=generator_name,
                generator_type=generator_type,
                in_service=in_service,
                unit_path=unit_path,
            )

        return GeneratorParameterRecord(
            generator_name=generator_name,
            generator_type=generator_type,
            in_service=in_service,
            unit_path=unit_path,
            kp=result.params.kp,
            ki=result.params.ki,
            kqv=result.params.kqv,
            rrpw=result.params.rrpw,
            damping_ratio=result.damping_ratio,
            bandwidth_hz=result.bandwidth_hz,
            natural_frequency_rad_s=(result.natural_frequency_rad_s),
        )


# =============================================================================
# Excel export
# =============================================================================


class ParameterExcelExporter:
    HEADERS = (
        "RunId",
        "GeneratorName",
        "GeneratorType",
        "InService",
        "DampingRatio",
        "Bandwidth_Hz",
        "NaturalFrequency_rad_s",
        "Kp",
        "Ki",
        "Kqv",
        "Rrpw",
    )

    def __init__(
        self,
        maximum_sheets_per_workbook: int = 100,
    ) -> None:
        if maximum_sheets_per_workbook <= 0:
            raise ValueError(
                "maximum_sheets_per_workbook " "must be greater than zero."
            )

        self.maximum_sheets_per_workbook = maximum_sheets_per_workbook

    def export(
        self,
        assignment: ParameterAssignment,
        output_directory: str | Path,
    ) -> list[Path]:
        assignment._require_execution()

        output_directory = Path(output_directory)

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        exported_files: list[Path] = []

        for start in range(
            0,
            len(assignment.runs),
            self.maximum_sheets_per_workbook,
        ):
            runs = assignment.runs[start : start + self.maximum_sheets_per_workbook]

            output_path = output_directory / (
                f"{assignment.name}_"
                f"{runs[0].run_id:06d}_"
                f"{runs[-1].run_id:06d}.xlsx"
            )

            self._save_workbook(
                runs=runs,
                output_path=output_path,
            )

            exported_files.append(output_path)

        return exported_files

    def _save_workbook(
        self,
        runs: tuple[ParameterRun, ...],
        output_path: Path,
    ) -> None:
        workbook = Workbook(write_only=True)

        for run in runs:
            worksheet = workbook.create_sheet(run.name)

            worksheet.append(self.HEADERS)

            for record in run:
                worksheet.append(
                    (
                        run.run_id,
                        record.generator_name,
                        record.generator_type,
                        record.in_service,
                        record.damping_ratio,
                        record.bandwidth_hz,
                        record.natural_frequency_rad_s,
                        record.kp,
                        record.ki,
                        record.kqv,
                        record.rrpw,
                    )
                )

        workbook.save(output_path)


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":

    from com_client import *

    emtp_client = EmtpComClient(attach_existing=True)

    emtp_object = emtp_client.emtp_object

    parameter_config = ParameterConfig(
        damping_ratio_range=ParameterRange(
            minimum=0.6,
            maximum=1.0,
        ),
        bandwidth_range=ParameterRange(
            minimum=2.5,
            maximum=15.0,
        ),
        kqv_range=ParameterRange(
            minimum=1.0,
            maximum=2.0,
        ),
        rrpw_range=ParameterRange(
            minimum=0.5,
            maximum=1.0,
        ),
    )

    parameter_assignment = ParameterAssignment(
        emtp_object=emtp_object,
        parameter_generator=ParameterGenerator(parameter_config),
        number_of_runs=100,
        name="ParametricRuns",
    )

    parameter_assignment.execute()

    first_run = parameter_assignment.get_run(1)

    for record in first_run:
        print(
            first_run.run_id,
            record.generator_name,
            record.parameters,
        )

    exporter = ParameterExcelExporter(
        maximum_sheets_per_workbook=100,
    )

    exported_files = exporter.export(
        assignment=parameter_assignment,
        output_directory=(Path(__file__).resolve().parent / "parametric_results"),
    )

    for exported_file in exported_files:
        print(f"Exported: {exported_file}")
