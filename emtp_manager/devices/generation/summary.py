"""Small, verified summary values for recognized generation chains."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import GenerationDevice, GenerationKind
from .form_data import FormDataFormatError, FormDataReader


@dataclass(frozen=True)
class GenerationSummary:
    """Read-only summary values suitable for the Generation grid."""

    capacity_mva: float | None
    capacity_source: str | None


class GenerationSummaryReader:
    """Read installed apparent-power capacity where its source is verified.

    WECC PV, Wind Park, and Inverter3P scripts define installed capacity as
    ``Ngen * Sgen`` and provide ``Sgen_unit``.  DER using the PV park follows
    the same contract. Other technologies remain empty until their own source
    is confirmed rather than guessed.
    """

    _UNIT_TO_MVA = {
        "VA": 1e-6,
        "KVA": 1e-3,
        "MVA": 1.0,
        "GVA": 1e3,
    }

    def __init__(self, form_data_reader: FormDataReader | None = None) -> None:
        self._form_data_reader = form_data_reader or FormDataReader()

    def read(self, device: GenerationDevice) -> GenerationSummary:
        if device.kind not in {
            GenerationKind.PHOTOVOLTAIC,
            GenerationKind.WIND,
            GenerationKind.DER,
            GenerationKind.BESS,
        }:
            return GenerationSummary(capacity_mva=None, capacity_source=None)
        try:
            snapshot = self._form_data_reader.read(device.unit_object)
        except FormDataFormatError:
            return GenerationSummary(capacity_mva=None, capacity_source=None)
        values = {parameter.key: parameter.value for parameter in snapshot.parameters}
        if "Ngen" not in values or "Sgen" not in values:
            return GenerationSummary(capacity_mva=None, capacity_source=None)
        try:
            count = float(values["Ngen"])
            rating = float(values["Sgen"])
        except ValueError:
            return GenerationSummary(capacity_mva=None, capacity_source=None)
        unit = values.get("Sgen_unit", "MVA").strip().upper()
        multiplier = self._UNIT_TO_MVA.get(unit)
        if multiplier is None:
            return GenerationSummary(capacity_mva=None, capacity_source=None)
        return GenerationSummary(
            capacity_mva=count * rating * multiplier,
            capacity_source="FormData: Ngen * Sgen",
        )
