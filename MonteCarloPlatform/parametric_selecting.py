from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from openpyxl import Workbook

from com_client import EmtpComClient
from emtp_utils import Design
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

    kp: float | None = None
    ki: float | None = None
    frt: int | None = None
    kqv: float | None = None

    settling_time: float | None = None
    settling_tolerance: float | None = None
    natural_frequency_rad_s: float | None = None
    bandwidth_hz: float | None = None

    attempts: int | None = None
    stop_threshold_reached: bool | None = None

    @property
    def has_parameters(self) -> bool:
        return self.in_service == 1

    @property
    def parameters(self) -> dict[str, float | int]:
        """Parameters that a future setter must apply to the EMTP unit."""
        if not self.has_parameters:
            return {}

        values = {
            "kp": self.kp,
            "ki": self.ki,
            "frt": self.frt,
            "kqv": self.kqv,
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

    def get_record(self, generator_name: str) -> GeneratorParameterRecord:
        try:
            return self.records_by_name[generator_name]
        except KeyError as error:
            raise KeyError(
                f"Generator '{generator_name}' not found in {self.name}."
            ) from error


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

        # Persistent output of the assignment.
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
        units = self._extract_units()

        self.runs = tuple(
            self._generate_run(
                run_id=run_id,
                units=units,
            )
            for run_id in range(1, self.number_of_runs + 1)
        )

        return self

    def get_run(self, run_id: int) -> ParameterRun:
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
        units: tuple[tuple[str, Any], ...],
    ) -> ParameterRun:
        return ParameterRun(
            run_id=run_id,
            records=tuple(
                self._generate_record(
                    generator_type=generator_type,
                    unit=unit,
                )
                for generator_type, unit in units
            ),
        )

    def _extract_units(self) -> tuple[tuple[str, Any], ...]:
        extractor = UnitExtractor(emtp_object=self.emtp_object)
        extractor.execute()

        units = tuple(
            [("PV", unit) for unit in extractor.units.pv_units]
            + [("WF", unit) for unit in extractor.units.wf_units]
            + [("BESS", unit) for unit in extractor.units.bess_units]
        )

        if not units:
            raise RuntimeError("No PV or WF units were found.")

        return units

    def _generate_record(
        self,
        generator_type: str,
        unit: Any,
    ) -> GeneratorParameterRecord:
        in_service = int(unit.get_in_service())
        generator_name = str(unit.object.name)

        if in_service not in (0, 1):
            raise ValueError(
                f"Invalid in-service value for " f"'{generator_name}': {in_service}."
            )

        result = self.parameter_generator.generate() if in_service == 1 else None

        return self._build_record(
            generator_name=generator_name,
            generator_type=generator_type,
            in_service=in_service,
            result=result,
        )

    @staticmethod
    def _build_record(
        generator_name: str,
        generator_type: str,
        in_service: int,
        result: ParameterResult | None,
    ) -> GeneratorParameterRecord:
        if result is None:
            return GeneratorParameterRecord(
                generator_name=generator_name,
                generator_type=generator_type,
                in_service=in_service,
            )

        return GeneratorParameterRecord(
            generator_name=generator_name,
            generator_type=generator_type,
            in_service=in_service,
            kp=result.params.kp,
            ki=result.params.ki,
            frt=result.params.frt,
            kqv=result.params.kqv,
            settling_time=result.settling_time,
            settling_tolerance=result.settling_tolerance,
            natural_frequency_rad_s=result.natural_frequency_rad_s,
            bandwidth_hz=result.bandwidth_hz,
            attempts=result.attempts,
            stop_threshold_reached=result.stop_threshold_reached,
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
        "Kp",
        "Ki",
        "FRT",
        "Kqv",
        "SettlingTime_s",
        "SettlingTolerance",
        "NaturalFrequency_rad_s",
        "Bandwidth_Hz",
        "Attempts",
        "StopThresholdReached",
    )

    def __init__(self, maximum_sheets_per_workbook: int = 250) -> None:
        if maximum_sheets_per_workbook <= 0:
            raise ValueError("maximum_sheets_per_workbook must be greater than zero.")

        self.maximum_sheets_per_workbook = maximum_sheets_per_workbook

    def export(
        self,
        assignment: ParameterAssignment,
        output_directory: str | Path,
    ) -> list[Path]:
        assignment._require_execution()

        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)

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
                        record.kp,
                        record.ki,
                        record.frt,
                        record.kqv,
                        record.settling_time,
                        record.settling_tolerance,
                        record.natural_frequency_rad_s,
                        record.bandwidth_hz,
                        record.attempts,
                        record.stop_threshold_reached,
                    )
                )

        workbook.save(output_path)


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    emtp_client = EmtpComClient(attach_existing=True)
    emtp_object = emtp_client.emtp_object

    # Design.open_design(emtp_object=emtp_object)

    parameter_config = ParameterConfig(
        settling_time_range=ParameterRange(
            minimum=0.030,
            maximum=0.150,
        ),
        damping_ratio_range=ParameterRange(
            minimum=0.6,
            maximum=0.8,
        ),
        kqv_range=ParameterRange(
            minimum=0.0,
            maximum=2.0,
        ),
        settling_tolerance=0.05,
        grid_voltage=1.0,
        minimum_bandwidth_hz=5.0,
        stop_bandwidth_hz=60.0,
        maximum_bandwidth_hz=60.0,
        maximum_attempts=10,
    )

    parameter_assignment = ParameterAssignment(
        emtp_object=emtp_object,
        parameter_generator=ParameterGenerator(parameter_config),
        number_of_runs=100,
        name="ParametricRuns",
    )

    parameter_assignment.execute()

    # Persistent access after execute().
    first_run = parameter_assignment.get_run(1)

    for record in first_run:
        print(
            first_run.run_id,
            record.generator_name,
            record.parameters,
        )

    exporter = ParameterExcelExporter(
        maximum_sheets_per_workbook=1000,
    )

    exported_files = exporter.export(
        assignment=parameter_assignment,
        output_directory=(Path(__file__).resolve().parent / "parametric_results"),
    )

    for exported_file in exported_files:
        print(f"Exported: {exported_file}")
