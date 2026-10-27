"""Read-only discovery of the generation object chains recognized by UnitExtractor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable


class GenerationKind(StrEnum):
    PHOTOVOLTAIC = "Photovoltaic"
    WIND = "Wind"
    BESS = "BESS"
    DER = "DER"
    SYNCHRONOUS = "Synchronous"


@dataclass(frozen=True)
class GenerationDevice:
    """One recognized generation template and its internal model reference.

    This is the Devices-domain representation.  It deliberately does not
    expose scenario-mask fields: those belong to Operational Scenario Manager.
    """

    kind: GenerationKind
    template_name: str
    template_lib_type: str
    internal_model_name: str
    internal_model_lib_type: str
    template_device: Any = field(repr=False, compare=False, default=None)
    internal_model_device: Any = field(repr=False, compare=False, default=None)

    @property
    def display_name(self) -> str:
        return self.template_name or self.internal_model_name

    @property
    def internal_model_path(self) -> str:
        return f"{self.template_name}/{self.internal_model_name}"


class GenerationDeviceCatalog:
    """Classify the same generation template families as ``UnitExtractor``."""

    def __init__(self, emtp_object: Any) -> None:
        self._emtp_object = emtp_object

    def discover(self) -> list[GenerationDevice]:
        """Return recognized object chains from the open circuit without writes."""
        circuit = self._emtp_object.currentCircuit
        if circuit is None:
            raise RuntimeError("No circuit is currently open.")
        parent_devices = getattr(circuit, "devices", None)
        if parent_devices is None:
            raise RuntimeError("No devices are available in the current circuit.")

        generation_devices: list[GenerationDevice] = []
        for parent_device in parent_devices:
            recognized = self._recognize(parent_device)
            if recognized is not None:
                generation_devices.append(recognized)
        return generation_devices

    def _recognize(self, parent_device: Any) -> GenerationDevice | None:
        parent_lib_type = self._attribute(parent_device, "LibType")
        if "TEMPLATE" not in parent_lib_type:
            return None

        if "PV_TEMPLATE" in parent_lib_type:
            return self._build_mask(
                GenerationKind.PHOTOVOLTAIC,
                parent_device,
                self._find_child_by_lib_type(parent_device, "WECC PV park"),
            )
        if "WT_TEMPLATE" in parent_lib_type or "WF_TEMPLATE" in parent_lib_type:
            return self._build_mask(
                GenerationKind.WIND,
                parent_device,
                self._find_child_by_lib_type(parent_device, "WECC Wind park"),
            )
        if "BESS_TEMPLATE" in parent_lib_type:
            return self._build_mask(
                GenerationKind.BESS,
                parent_device,
                self._find_child_by_lib_type(parent_device, "AC-DC converter with control"),
            )
        if "DER_TEMPLATE" in parent_lib_type:
            return self._build_mask(
                GenerationKind.DER,
                parent_device,
                self._find_child_by_lib_type(parent_device, "WECC PV park"),
            )
        if "SG" in parent_lib_type:
            return self._recognize_synchronous(parent_device)
        return None

    def _recognize_synchronous(self, parent_device: Any) -> GenerationDevice | None:
        children = tuple(self._children(parent_device))
        machine = next(
            (
                child
                for child in children
                if "Synchronous" in self._attribute(child, "LibType")
                and "SM" in self._attribute(child, "Part")
            ),
            None,
        )
        has_load_flow = any(
            self._attribute(child, "LibType") == "Load-Flow Bus" for child in children
        )
        has_transformer = any("TR_" in self._attribute(child, "Name") for child in children)
        if machine is None or not has_load_flow or not has_transformer:
            return None
        return self._build_mask(GenerationKind.SYNCHRONOUS, parent_device, machine)

    def _build_mask(
        self,
        kind: GenerationKind,
        parent_device: Any,
        internal_model_device: Any | None,
    ) -> GenerationDevice | None:
        if internal_model_device is None:
            return None
        parent_name = self._attribute(parent_device, "Name")
        internal_model_name = self._attribute(internal_model_device, "Name")
        return GenerationDevice(
            kind=kind,
            template_name=parent_name,
            template_lib_type=self._attribute(parent_device, "LibType"),
            internal_model_name=internal_model_name,
            internal_model_lib_type=self._attribute(internal_model_device, "LibType"),
            template_device=parent_device,
            internal_model_device=internal_model_device,
        )

    def _find_child_by_lib_type(self, parent_device: Any, lib_type: str) -> Any | None:
        return next(
            (
                child
                for child in self._children(parent_device)
                if self._attribute(child, "LibType") == lib_type
            ),
            None,
        )

    @staticmethod
    def _children(parent_device: Any) -> Iterable[Any]:
        sub_circuit = getattr(parent_device, "subCircuit", None)
        devices = getattr(sub_circuit, "devices", None)
        return devices if devices is not None else ()

    @staticmethod
    def _attribute(device: Any, name: str) -> str:
        value = device.getAttribute(name)
        return "" if value is None else str(value)
