"""Translate platform parameters into EMTP device parameters for one run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from emtp_utils import Utils

from .task import UnitParameters, WorkerInput


@dataclass(frozen=True, slots=True)
class DeviceParameterChange:
    """One complete parameter update for one EMTP device."""

    device_path: str
    generator_type: str
    parameters: dict[str, str]


@dataclass(frozen=True, slots=True)
class PlantSetterReport:
    """Evidence of the device updates requested for one worker run."""

    study_id: str
    run_id: int
    changes: tuple[DeviceParameterChange, ...]


class PlantSetter:
    """Apply the parameter values of a :class:`WorkerInput` to EMTP.

    PV, WF and DER write the REGC_A and REGC_C fields together. EMTP uses the
    fields associated with its selected converter model; the other fields do
    not affect the active control model.
    """

    _WECC_PLL_PARAMETERS: Mapping[str, tuple[str, ...]] = {
        "kp": ("Kppll_REGC_A", "Kppll_REGC_C"),
        "ki": ("Kipll_REGC_A", "Kipll_REGC_C"),
        "kqv": ("Kqv",),
        "rrpw": ("Rrpwr_REGC_A", "rrpwr_REGC_C"),
    }
    _BESS_PARAMETERS: Mapping[str, tuple[str, ...]] = {
        "kp": ("PLLinv_kp",),
        "ki": ("PLLinv_ki",),
        "kqv": ("VoltReg_FRT_Gain",),
    }
    _PARAMETER_MAPPINGS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
        "PV": _WECC_PLL_PARAMETERS,
        "DER": _WECC_PLL_PARAMETERS,
        "WF": _WECC_PLL_PARAMETERS,
        "BESS": _BESS_PARAMETERS,
    }

    def __init__(self, emtp_object: Any) -> None:
        self.emtp_object = emtp_object

    def apply(self, worker_input: WorkerInput) -> PlantSetterReport:
        """Translate and apply every active unit in one worker input."""

        changes = self.build_changes(worker_input)

        for change in changes:
            Utils.set_params_from_dict_by_path(
                self.emtp_object,
                change.device_path,
                change.parameters,
            )
        return PlantSetterReport(
            study_id=worker_input.study_id,
            run_id=worker_input.run_id,
            changes=changes,
        )

    def build_changes(
        self,
        worker_input: WorkerInput,
    ) -> tuple[DeviceParameterChange, ...]:
        """Build the EMTP updates without reading or changing the design."""
        changes: list[DeviceParameterChange] = []
        for unit in worker_input.units:
            change = self._build_unit_change(unit)
            if change is not None:
                changes.append(change)
        return tuple(changes)

    def _build_unit_change(
        self,
        unit: UnitParameters,
    ) -> DeviceParameterChange | None:
        if unit.in_service == 0:
            return None

        mapping = self._PARAMETER_MAPPINGS.get(unit.generator_type)
        if mapping is None:
            raise ValueError(f"Unsupported generator type: {unit.generator_type}")

        emtp_parameters: dict[str, str] = {}
        for platform_name, emtp_names in mapping.items():
            value = unit.parameters.get(platform_name)
            if value is None:
                continue
            for emtp_name in emtp_names:
                emtp_parameters[emtp_name] = str(value)

        if not emtp_parameters:
            return None

        return DeviceParameterChange(
            device_path=unit.unit_path,
            generator_type=unit.generator_type,
            parameters=emtp_parameters,
        )
