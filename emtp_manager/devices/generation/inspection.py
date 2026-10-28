"""Read-only parameter inspectors for non-PV generation device families."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .catalog import GenerationDevice, GenerationKind
from .form_data import FormDataReader


@dataclass(frozen=True)
class InspectedParameter:
    key: str
    value: str
    source: str


@dataclass(frozen=True)
class InspectedParameterSet:
    all_parameters: tuple[InspectedParameter, ...]
    summary_parameters: tuple[InspectedParameter, ...]


class BessParameterReader:
    """Read BESS/Inverter3P XML FormData without invoking oDevice."""

    _SUMMARY_KEYS = ("Ngen", "Sgen", "Sgen_unit", "Pref_poi", "Qref_pu", "converterModel")

    def __init__(self, form_data_reader: FormDataReader | None = None) -> None:
        self._form_data_reader = form_data_reader or FormDataReader()

    def read(self, device: GenerationDevice) -> InspectedParameterSet:
        if device.kind != GenerationKind.BESS:
            raise ValueError("BessParameterReader requires a BESS device.")
        snapshot = self._form_data_reader.read(device.unit_object)
        parameters = tuple(
            InspectedParameter(parameter.key, parameter.value, "FormData")
            for parameter in snapshot.parameters
        )
        values = {parameter.key: parameter for parameter in parameters}
        return InspectedParameterSet(
            all_parameters=parameters,
            summary_parameters=tuple(
                values[key] for key in self._SUMMARY_KEYS if key in values
            ),
        )


class SynchronousParameterReader:
    """Read machine_sm tagged FormData and ModelData without oDevice execution."""

    _TAG_PATTERN = re.compile(r"(?:^|\n)([A-Za-z][A-Za-z0-9_]*)=([^,\n]*),?")
    _SUMMARY_KEYS = ("R", "MS", "MSu")

    def read(self, device: GenerationDevice) -> InspectedParameterSet:
        if device.kind != GenerationKind.SYNCHRONOUS:
            raise ValueError("SynchronousParameterReader requires a Synchronous device.")
        parameters = (
            *self._read_attribute(device.unit_object, "FormData"),
            *self._read_attribute(device.unit_object, "ModelData"),
        )
        summary = tuple(
            parameter
            for parameter in parameters
            if parameter.source == "ModelData" and parameter.key in self._SUMMARY_KEYS
        )
        return InspectedParameterSet(
            all_parameters=parameters,
            summary_parameters=summary,
        )

    def _read_attribute(
        self, unit_object: Any, attribute_name: str
    ) -> tuple[InspectedParameter, ...]:
        raw_data = unit_object.getAttribute(attribute_name) or ""
        return tuple(
            InspectedParameter(match.group(1), match.group(2).strip(), attribute_name)
            for match in self._TAG_PATTERN.finditer(str(raw_data))
        )
