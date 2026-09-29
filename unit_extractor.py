from dataclasses import dataclass, field
from emtp_utils import *
from com_client import *
from unit_models import *

from typing import List
from pathlib import Path
import openpyxl


@dataclass
class UnitManager:

    pv_units: List[Photovoltaic] = field(default_factory=list)
    wf_units: List[WindTurbine] = field(default_factory=list)
    bess_units: List[Bess] = field(default_factory=list)
    syn_units: List[Synchronous] = field(default_factory=list)
    der_units: List[Der] = field(default_factory=list)
    load_units: List[Load] = field(default_factory=list)


class UnitExtractor:

    def __init__(self, emtp_object):

        self.emtp_object = emtp_object
        self.units = UnitManager()

    def _get_devices(self):

        cct = self.emtp_object.currentCircuit
        self.parent_devices = cct.devices

    def _classify_devices(self):

        for parent_device in self.parent_devices:

            # Ensure a new unit to process
            device = None

            if "TEMPLATE" in parent_device.getAttribute("LibType"):
                if "PV_TEMPLATE" in parent_device.getAttribute("LibType"):

                    for device in parent_device.subCircuit.devices:
                        if device.getAttribute("LibType") == "WECC PV park":
                            child_device = device
                            break

                    if child_device:
                        device = Photovoltaic(
                            object=parent_device, unit_object=child_device
                        )
                        self.units.pv_units.append(device)

                    child_device = None

                elif "WT_TEMPLATE" in parent_device.getAttribute(
                    "LibType"
                ) or "WF_TEMPLATE" in parent_device.getAttribute("LibType"):

                    for device in parent_device.subCircuit.devices:
                        if device.getAttribute("LibType") == "WECC Wind park":
                            child_device = device
                            break

                    if child_device:
                        device = WindTurbine(
                            object=parent_device, unit_object=child_device
                        )
                        self.units.wf_units.append(device)

                    child_device = None

                elif "BESS_TEMPLATE" in parent_device.getAttribute("LibType"):

                    for device in parent_device.subCircuit.devices:
                        if (
                            device.getAttribute("LibType")
                            == "AC-DC converter with control"
                        ):
                            child_device = device
                            break

                    if child_device:
                        device = Bess(object=parent_device, unit_object=child_device)
                        self.units.bess_units.append(device)

                    child_device = None

                elif "DER_TEMPLATE" in parent_device.getAttribute("LibType"):

                    for device in parent_device.subCircuit.devices:
                        if device.getAttribute("LibType") == "WECC PV park":
                            child_device = device
                            break

                    if child_device:
                        device = Der(object=parent_device, unit_object=child_device)
                        self.units.der_units.append(device)

                    child_device = None

                elif "SG" in parent_device.getAttribute(
                    "LibType"
                ) and "TEMPLATE" in parent_device.getAttribute("LibType"):

                    subcct = parent_device.subCircuit

                    # Pre-define variable
                    syn_unit = None
                    lf_unit = None
                    trf_unit = None
                    load_unit = None

                    for device in subcct.devices:

                        if "Synchronous" in device.getAttribute(
                            "LibType"
                        ) and "SM" in device.getAttribute("Part"):
                            syn_unit = device

                        elif device.getAttribute("LibType") == "Load-Flow Bus":
                            lf_unit = device

                        elif "TR_" in device.getAttribute("Name"):
                            trf_unit = device

                        try:
                            if device.getAttribute("Part") == "PQload":
                                load_unit = device
                            else:
                                load_unit = None
                        except:
                            load_unit = None

                    if syn_unit and lf_unit and trf_unit:

                        device = Synchronous(
                            object=parent_device,
                            unit_object=syn_unit,
                            loadflow_object=lf_unit,
                            trf_object=trf_unit,
                            load_object=load_unit,
                        )

                        self.units.syn_units.append(device)

                        syn_unit = None
                        lf_unit = None
                        trf_unit = None
                        load_unit = None

                    else:
                        print(
                            f"Error: {parent_device.name} does not have a synchronous, load-flow unit or transformer associated"
                        )
                        syn_unit = None
                        lf_unit = None
                        trf_unit = None
                        load_unit = None

            elif "PQ load" in parent_device.getAttribute(
                "LibType"
            ) or "EDAC" in parent_device.getAttribute("LibType"):

                if "PQ" in parent_device.getAttribute("LibType"):
                    child_device = parent_device
                    parent_device = ""
                    device = Load(object=parent_device, load_object=child_device)
                    device.object = None
                    self.units.load_units.append(device)

                else:
                    child_device = ""
                    device = Load(object=parent_device, load_object=child_device)
                    device.load_object = None
                    self.units.load_units.append(device)

                child_device = None

            else:
                continue

    def execute(self):

        self._get_devices()
        self._classify_devices()


if __name__ == "__main__":

    emtp_client = EmtpComClient(attach_existing=True)
    emtp_object = emtp_client.emtp_object

    extractor = UnitExtractor(emtp_object=emtp_object)
    extractor.execute()

    loads = extractor.units.load_units
    for load in loads:
        print(load)
