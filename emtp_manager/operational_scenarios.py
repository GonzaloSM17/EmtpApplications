"""Read-only operational-scenario masks, separated from device management.

The existing unit methods edit ``XMLDataGrids`` on the upper/template object.
This module models that boundary without changing any attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from emtp_manager.devices.generation.catalog import (
    GenerationDevice,
    GenerationDeviceCatalog,
    GenerationKind,
)


@dataclass(frozen=True)
class OperationalScenarioMask:
    """A scenario/operating-point mask stored on a generation template."""

    kind: GenerationKind
    mask_host_name: str
    mask_host_lib_type: str
    internal_model_name: str
    internal_model_lib_type: str
    mask_attribute: str = "XMLDataGrids"
    mask_host_device: Any = field(repr=False, compare=False, default=None)
    internal_model_device: Any = field(repr=False, compare=False, default=None)

    @property
    def internal_model_path(self) -> str:
        return f"{self.mask_host_name}/{self.internal_model_name}"

    def get_zone(self) -> str:
        """Read Zone from the upper/template object, not XMLDataGrids."""
        return self.mask_host_device.getAttribute("Zone") or ""

    def set_zone(self, value: str) -> None:
        """Set Zone directly on the upper/template object."""
        self.mask_host_device.setAttribute("Zone", str(value))

    @classmethod
    def from_generation_device(cls, device: GenerationDevice) -> "OperationalScenarioMask":
        return cls(
            kind=device.kind,
            mask_host_name=device.template_name,
            mask_host_lib_type=device.template_lib_type,
            internal_model_name=device.internal_model_name,
            internal_model_lib_type=device.internal_model_lib_type,
            mask_host_device=device.template_device,
            internal_model_device=device.internal_model_device,
        )


@dataclass(frozen=True)
class OperationalScenarioValue:
    """A recognized editable value read from an upper-template XML grid."""

    kind: GenerationKind
    object_name: str
    parameter: str
    value: str
    mask_attribute: str = "XMLDataGrids"


@dataclass(frozen=True)
class OperationalScenarioRecord:
    """Current scenario values and their source mask, before any UI draft."""

    mask: OperationalScenarioMask
    values: dict[str, str]
    raw_xml_data_grids: str
    zone: str


@dataclass(frozen=True)
class OperationalScenarioChange:
    """A staged update to one upper-template scenario mask."""

    record: OperationalScenarioRecord
    parameter_values: dict[str, str]
    zone: str | None = None


class OperationalScenarioManager:
    """Enumerate masks that will later receive scenario-level editing only."""

    def __init__(self, emtp_object: Any) -> None:
        self._emtp_object = emtp_object

    def discover_generation_masks(self) -> list[OperationalScenarioMask]:
        devices = GenerationDeviceCatalog(self._emtp_object).discover()
        return [OperationalScenarioMask.from_generation_device(device) for device in devices]

    def load_generation_values(self) -> list[OperationalScenarioValue]:
        """Read only the scenario fields currently supported by unit methods.

        The first XML grid is interpreted exactly as ``XmlDevice.get_param``:
        parameter name in cell 1 and value in cell 2. Other grids are not
        parsed or changed here.
        """
        values: list[OperationalScenarioValue] = []
        for record in self.load_generation_records():
            for parameter, value in record.values.items():
                if parameter in self._settable_parameters(record.mask.kind):
                    values.append(
                        OperationalScenarioValue(
                            kind=record.mask.kind,
                            object_name=record.mask.mask_host_name,
                            parameter=parameter,
                            value=value,
                        )
                    )
        return values

    def load_generation_records(self) -> list[OperationalScenarioRecord]:
        """Read every recognized generation mask and its supported values."""
        records: list[OperationalScenarioRecord] = []
        for mask in self.discover_generation_masks():
            raw_xml_data_grids = (
                mask.mask_host_device.getAttribute(mask.mask_attribute) or ""
            )
            values = self._first_grid_values_from_raw(mask, raw_xml_data_grids)
            supported_values = {
                parameter: values[parameter]
                for parameter in self._settable_parameters(mask.kind)
                if parameter in values
            }
            records.append(
                OperationalScenarioRecord(
                    mask=mask,
                    values=supported_values,
                    raw_xml_data_grids=str(raw_xml_data_grids),
                    zone=mask.get_zone(),
                )
            )
        return records

    def apply_generation_changes(
        self, changes: Iterable[OperationalScenarioChange]
    ) -> None:
        """Apply validated drafts and restore prior writes if one object fails."""
        plans: list[tuple[OperationalScenarioChange, str, str, str]] = []
        for change in changes:
            record = change.record
            current_raw = (
                record.mask.mask_host_device.getAttribute(record.mask.mask_attribute)
                or ""
            )
            if str(current_raw) != record.raw_xml_data_grids:
                raise RuntimeError(
                    f"Scenario mask for {record.mask.mask_host_name!r} changed in EMTP. "
                    "Reload before applying drafts."
                )
            if record.mask.get_zone() != record.zone:
                raise RuntimeError(
                    f"Zone for {record.mask.mask_host_name!r} changed in EMTP. "
                    "Reload before applying drafts."
                )
            normalized_values = self._normalize_values(
                record.mask.kind, change.parameter_values
            )
            updated_raw = self._update_first_grid(
                record.mask, record.raw_xml_data_grids, normalized_values
            )
            updated_zone = record.zone if change.zone is None else change.zone.strip()
            plans.append((change, updated_raw, updated_zone, record.zone))

        written: list[tuple[OperationalScenarioChange, str, str]] = []
        try:
            for change, updated_raw, updated_zone, original_zone in plans:
                record = change.record
                written.append((change, record.raw_xml_data_grids, original_zone))
                if updated_zone != original_zone:
                    record.mask.set_zone(updated_zone)
                if updated_raw != record.raw_xml_data_grids:
                    record.mask.mask_host_device.setAttribute(
                        record.mask.mask_attribute, updated_raw
                    )
        except Exception as exc:
            for change, original_raw, original_zone in reversed(written):
                try:
                    change.record.mask.set_zone(original_zone)
                    change.record.mask.mask_host_device.setAttribute(
                        change.record.mask.mask_attribute, original_raw
                    )
                except Exception:
                    pass
            raise RuntimeError(
                f"Scenario changes failed and previously written masks were restored: {exc}"
            ) from exc

    @staticmethod
    def _settable_parameters(kind: GenerationKind) -> tuple[str, ...]:
        common = ("in_service", "p_setpoint", "q_setpoint")
        if kind is GenerationKind.SYNCHRONOUS:
            return common + ("v_setpoint", "bus_type")
        return common

    @staticmethod
    def _first_grid_values(mask: OperationalScenarioMask) -> dict[str, str]:
        raw_grids = mask.mask_host_device.getAttribute(mask.mask_attribute) or ""
        return OperationalScenarioManager._first_grid_values_from_raw(mask, str(raw_grids))

    @staticmethod
    def _first_grid_values_from_raw(
        mask: OperationalScenarioMask, raw_grids: str
    ) -> dict[str, str]:
        first_grid = raw_grids.split("<XMLStringSeparator>", 1)[0]
        if not first_grid.strip():
            return {}
        try:
            root = ET.fromstring(first_grid)
        except ET.ParseError as exc:
            raise RuntimeError(
                f"Invalid {mask.mask_attribute} on {mask.mask_host_name!r}: {exc}"
            ) from exc

        values: dict[str, str] = {}
        for row in root.findall("row"):
            cells = row.findall("cell")
            if len(cells) < 3:
                continue
            parameter = (cells[1].text or "").strip()
            if parameter:
                values[parameter] = (cells[2].text or "").strip()
        return values

    @staticmethod
    def _normalize_values(
        kind: GenerationKind, values: dict[str, str]
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for parameter, raw_value in values.items():
            value = str(raw_value).strip()
            if parameter == "in_service":
                if value not in {"0", "1"}:
                    raise ValueError("Status must be 0 or 1.")
                normalized[parameter] = value
            elif parameter in {"p_setpoint", "q_setpoint"}:
                normalized[parameter] = str(round(float(value), 1))
            elif parameter == "v_setpoint":
                if kind is not GenerationKind.SYNCHRONOUS:
                    raise ValueError("Voltage Setpoint applies only to synchronous units.")
                voltage = round(float(value), 2)
                normalized[parameter] = str(min(1.05, max(0.95, voltage)))
            elif parameter == "bus_type":
                if kind is not GenerationKind.SYNCHRONOUS:
                    raise ValueError("Bus Type applies only to synchronous units.")
                bus_type = {"PQ": "1", "PV": "2", "SLACK": "3"}.get(
                    value.upper(), value
                )
                if bus_type not in {"1", "2", "3"}:
                    raise ValueError("Bus Type must be PQ, PV, Slack, 1, 2 or 3.")
                normalized[parameter] = bus_type
            else:
                raise ValueError(f"Unsupported scenario parameter: {parameter}")
        return normalized

    @staticmethod
    def _update_first_grid(
        mask: OperationalScenarioMask,
        raw_grids: str,
        parameter_values: dict[str, str],
    ) -> str:
        if not parameter_values:
            return raw_grids
        split_grids = raw_grids.split("<XMLStringSeparator>")
        try:
            root = ET.fromstring(split_grids[0])
        except ET.ParseError as exc:
            raise RuntimeError(
                f"Invalid {mask.mask_attribute} on {mask.mask_host_name!r}: {exc}"
            ) from exc
        remaining = set(parameter_values)
        for row in root.findall("row"):
            cells = row.findall("cell")
            if len(cells) < 3:
                continue
            parameter = (cells[1].text or "").strip()
            if parameter in parameter_values:
                cells[2].text = parameter_values[parameter]
                remaining.discard(parameter)
        if remaining:
            raise RuntimeError(
                f"Parameter(s) absent from {mask.mask_host_name!r}: {', '.join(sorted(remaining))}"
            )
        split_grids[0] = ET.tostring(root, encoding="unicode")
        return "<XMLStringSeparator>".join(split_grids)
