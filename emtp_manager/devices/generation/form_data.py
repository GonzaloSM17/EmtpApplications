"""Read-only access to EMTP ``FormData`` stored on internal unit objects.

The Renewables oDevice scripts serialize their user-facing parameter object as
XML in the ``FormData`` attribute.  This module intentionally only reads that
source.  Reproducing an oDevice ``SaveData()`` call is a separate operation.
"""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET
from typing import Any


class FormDataFormatError(ValueError):
    """Raised when an internal device exposes non-XML FormData."""


@dataclass(frozen=True)
class FormDataParameter:
    """One source parameter stored by the oDevice in FormData."""

    key: str
    value: str


@dataclass(frozen=True)
class FormDataSnapshot:
    """An immutable read of an internal unit object's FormData attribute."""

    unit_name: str
    parameters: tuple[FormDataParameter, ...]

    def value_for(self, key: str) -> str | None:
        """Return a parameter value by its EMTP key, if present."""
        return next(
            (parameter.value for parameter in self.parameters if parameter.key == key),
            None,
        )


class FormDataReader:
    """Parse the XML contract used by Renewables ``SaveFormDataXML.js``."""

    attribute_name = "FormData"

    def read(self, unit_object: Any) -> FormDataSnapshot:
        """Read a unit object's current FormData without modifying EMTP."""
        unit_name = self._attribute(unit_object, "Name")
        raw_form_data = self._attribute(unit_object, self.attribute_name).strip()
        if not raw_form_data:
            return FormDataSnapshot(unit_name=unit_name, parameters=())
        return FormDataSnapshot(
            unit_name=unit_name,
            parameters=self.parse(raw_form_data),
        )

    @staticmethod
    def parse(raw_form_data: str) -> tuple[FormDataParameter, ...]:
        """Parse ``<Parameters><key value="..."/></Parameters>`` XML."""
        try:
            root = ET.fromstring(raw_form_data)
        except ET.ParseError as exc:
            raise FormDataFormatError(
                "FormData is not valid XML; this device cannot yet be read by "
                "the XML FormData adapter."
            ) from exc

        parameters_node = root if root.tag == "Parameters" else root.find(".//Parameters")
        if parameters_node is None:
            raise FormDataFormatError("FormData does not contain a Parameters XML node.")

        return tuple(
            FormDataParameter(key=child.tag, value=child.attrib.get("value", ""))
            for child in parameters_node
            if isinstance(child.tag, str)
        )

    @staticmethod
    def _attribute(device: Any, name: str) -> str:
        value = device.getAttribute(name)
        return "" if value is None else str(value)
