from emtp_utils import *
from com_client import *

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class XmlDevice:
    """Base dataclass for EMTP objects that expose parameters via XMLDataGrids."""

    object: Any = None

    XML_SEPARATOR = "<XMLStringSeparator>"

    def __post_init__(self):
        if self.object is None:
            raise ValueError(f"{self.__class__.__name__} object cannot be None.")

    @property
    def xml_data_grids_raw(self) -> str:
        return self.object.getAttribute("XMLDataGrids") or ""

    def set_xml_data_grids_raw(self, value: str) -> None:
        self.object.setAttribute("XMLDataGrids", value)

    def _split_grids(self) -> tuple[str, list[str]]:
        parts = self.xml_data_grids_raw.split(self.XML_SEPARATOR)
        return parts[0], parts[1:]

    def _join_grids(self, first_grid: str, other_grids: list[str]) -> str:
        if not other_grids:
            return first_grid
        return first_grid + self.XML_SEPARATOR + self.XML_SEPARATOR.join(other_grids)

    def _load_initial_grid(self) -> tuple[ET.Element, list[str]]:
        first_grid, other_grids = self._split_grids()
        return ET.fromstring(first_grid), other_grids

    def set_param(self, name: str, value: Any) -> None:
        root, other_grids = self._load_initial_grid()

        for row in root.findall("row"):
            cells = row.findall("cell")

            if len(cells) < 3:
                continue

            param_name = (cells[1].text or "").strip()

            if param_name == name:
                cells[2].text = str(value)

                new_first_grid = ET.tostring(root, encoding="unicode")
                new_raw = self._join_grids(new_first_grid, other_grids)

                self.set_xml_data_grids_raw(new_raw)
                return

        raise RuntimeError(f"Parameter not found in XMLDataGrids: {name}")

    def get_param(self, name: str) -> str:
        root, _ = self._load_initial_grid()

        for row in root.findall("row"):
            cells = row.findall("cell")

            if len(cells) < 3:
                continue

            param_name = (cells[1].text or "").strip()

            if param_name == name:
                return (cells[2].text or "").strip()

        raise RuntimeError(f"Parameter not found in XMLDataGrids: {name}")


@dataclass
class EmtpLoad(XmlDevice):

    load_object: Any = None

    @property
    def name(self) -> str:
        if self.object:
            return self.object.getAttribute("Name")
        elif self.load_object:
            return self.load_object.getAttribute("Name")
        else:
            return None

    @property
    def libtype(self) -> str:
        return self.load_object.getAttribute("LibType")


# General classes for set and get attributes
@dataclass
class EmtpUnit(XmlDevice):
    """Base class for all EMTP units."""

    unit_object: Any = None

    @property
    def name(self) -> str:
        if self.object:
            return self.object.getAttribute("Name")
        elif self.unit_object:
            return self.unit_object.getAttribute("Name")

    @property
    def libtype(self) -> str:
        return self.unit_object.getAttribute("LibType")


@dataclass
class RenewableEnergySource(EmtpUnit):
    """Base class for all renewable energy sources."""

    def set_in_service(self, flag: int) -> None:
        self.set_param("in_service", int(flag))

    def set_p(self, value: float) -> None:
        value = round(value, 1)
        self.set_param("p_setpoint", value)

    # def set_q_control_mode(self, mode: int) -> None:
    #     if mode not in [1, 2, 3]:
    #         raise ValueError("Invalid Q control mode")
    #     self.set_param("q_control_mode", int(mode))

    def set_q(self, value: float) -> None:
        value = round(value, 1)
        self.set_param("q_setpoint", value)

    # def set_v(self, value: float) -> None:
    #     value = round(value, 2)
    #     self.set_param("v_setpoint", value)

    # def set_pf(self, value: float) -> None:
    #     value = round(value, 3)
    #     self.set_param("pf_poi", value)

    # def set_p_f_control_mode(self, mode: int) -> None:
    #     if mode not in [0, 1]:
    #         raise ValueError("Invalid p_f_control_mode")
    #     self.set_param("p_f_control_mode", int(mode))

    def get_in_service(self) -> int:
        return self.get_param("in_service")

    def get_p(self) -> float:
        return self.get_param("p_setpoint")

    def get_q(self) -> float:
        return self.get_param("q_setpoint")

    @property
    def unit_path(self):
        return self.object.name + "/" + self.unit_object.name


@dataclass
class SynchronousSource(EmtpUnit):

    loadflow_object: Any = None
    trf_object: Any = None
    load_object: Any = None

    def set_in_service(self, flag: int) -> None:
        self.set_param("in_service", int(flag))

    def set_p(self, value: float) -> None:
        value = round(value, 1)
        self.set_param("p_setpoint", value)

    def set_bus_type(self, mode: int) -> None:
        if mode not in [1, 2, 3]:
            raise ValueError("Invalid bus type (must be 1=PQ, 2=PV, or 3=Slack)")
        self.set_param("bus_type", int(mode))

    def set_q(self, value: float) -> None:
        value = round(value, 1)
        self.set_param("q_setpoint", value)

    def set_v(self, value: float) -> None:
        value = round(value, 2)

        # Limit by grid-code
        if value < 0.95:
            value = 0.95

        elif value > 1.05:
            value = 1.05

        else:
            value = value

        # set value
        self.set_param("v_setpoint", value)

    def get_p(self) -> float:
        return self.get_param("p_setpoint")

    def get_q(self) -> float:
        return self.get_param("q_setpoint")

    def get_v(self) -> float:
        return self.get_param("v_setpoint")

    def get_in_service(self) -> float:
        return self.get_param("in_service")

    def get_bus_type(self) -> float:

        bus_type = self.get_param("bus_type")

        if bus_type == 1 or bus_type == "1":
            return "PQ"
        elif bus_type == 2 or bus_type == "2":
            return "PV"
        elif bus_type == 3 or bus_type == "3":
            return "Slack"

    @property
    def unit_path(self) -> str:
        return self.object.name + "/" + self.unit_object.name

    @property
    def loadflow_path(self) -> str:
        return self.object.name + "/" + self.loadflow_object.name

    @property
    def trf_path(self) -> str:
        return self.object.name + "/" + self.trf_object.name

    @property
    def load_path(self) -> str:
        return self.object.name + "/" + self.load_object.name


# Class for EMTP classify
@dataclass
class Photovoltaic(RenewableEnergySource):
    pass


@dataclass
class WindTurbine(RenewableEnergySource):
    pass


@dataclass
class Bess(RenewableEnergySource):
    pass


@dataclass
class Der(RenewableEnergySource):
    pass


@dataclass
class Synchronous(SynchronousSource):
    pass


@dataclass
class Load(EmtpLoad):

    def get_in_service(self) -> int:
        if self.object:
            in_service = self.object.getAttribute("Exclude")
            return 0 if in_service == "Ex" else 1

        elif self.load_object:
            in_service = self.load_object.getAttribute("Exclude")
            return 0 if in_service == "Ex" else 1

        return 1

    def get_p(self) -> float:

        if self.object:
            return self.get_param("Load_fixed")

        return 0.0

    def get_q(self) -> float:

        if self.object:
            return self.get_param("Reactive_Load")
        return 0.0

    @property
    def load_path(self) -> str:

        if self.load_object:
            return self.load_object.getAttribute("Name")
        else:
            return None
