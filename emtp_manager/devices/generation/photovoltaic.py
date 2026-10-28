"""Read-only photovoltaic parameter access from a PV ``unit_object``."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import GenerationDevice, GenerationKind
from .form_data import FormDataParameter, FormDataReader, FormDataSnapshot


PHOTOVOLTAIC_SUMMARY_KEYS = (
    "Ngen",
    "Sgen",
    "Vpoi_kVRMSLL",
    "Vgrid_kVRMSLL",
    "QC_select",
    "Qpoi_pu",
    "PC_select",
    "Pref_poi",
    "Irradiance",
    "Temp",
    "converterModel",
)


@dataclass(frozen=True)
class PhotovoltaicParameterSet:
    """PV FormData plus a deliberately small set for the device summary."""

    snapshot: FormDataSnapshot

    @property
    def all_parameters(self) -> tuple[FormDataParameter, ...]:
        return self.snapshot.parameters

    @property
    def summary_parameters(self) -> tuple[FormDataParameter, ...]:
        values = {parameter.key: parameter for parameter in self.snapshot.parameters}
        return tuple(values[key] for key in PHOTOVOLTAIC_SUMMARY_KEYS if key in values)


class PhotovoltaicParameterReader:
    """Read PV source parameters.  No FormData or model state is written."""

    def __init__(self, form_data_reader: FormDataReader | None = None) -> None:
        self._form_data_reader = form_data_reader or FormDataReader()

    def read(self, device: GenerationDevice) -> PhotovoltaicParameterSet:
        if device.kind is not GenerationKind.PHOTOVOLTAIC:
            raise ValueError("PhotovoltaicParameterReader requires a Photovoltaic device.")
        return PhotovoltaicParameterSet(self._form_data_reader.read(device.unit_object))
