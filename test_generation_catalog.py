from dataclasses import dataclass, field
import unittest

from emtp_manager.devices.generation import GenerationDeviceCatalog, GenerationKind
from emtp_manager.operational_scenarios import (
    OperationalScenarioChange,
    OperationalScenarioManager,
)


@dataclass
class FakeCircuit:
    devices: list[object] = field(default_factory=list)


class FakeDevice:
    def __init__(self, attributes: dict[str, str], children: list["FakeDevice"] | None = None) -> None:
        self._attributes = attributes
        self.subCircuit = FakeCircuit(children or [])

    def getAttribute(self, name: str) -> str:
        return self._attributes.get(name, "")

    def setAttribute(self, name: str, value: str) -> None:
        self._attributes[name] = value


class FakeEmtpObject:
    def __init__(self, devices: list[FakeDevice]) -> None:
        self.currentCircuit = FakeCircuit(devices)


def child(name: str, lib_type: str, part: str = "") -> FakeDevice:
    return FakeDevice({"Name": name, "LibType": lib_type, "Part": part})


class GenerationCatalogTests(unittest.TestCase):
    def test_recognizes_every_generation_family_from_unit_extractor(self) -> None:
        pv = FakeDevice(
            {
                "Name": "PV_A",
                "LibType": "PV_TEMPLATE",
                "XMLDataGrids": (
                    "<grid>"
                    "<row><cell>0</cell><cell>in_service</cell><cell>1</cell></row>"
                    "<row><cell>1</cell><cell>p_setpoint</cell><cell>125.5</cell></row>"
                    "<row><cell>2</cell><cell>q_setpoint</cell><cell>-3.0</cell></row>"
                    "</grid><XMLStringSeparator>untouched-grid"
                ),
            },
            [child("PV mask", "WECC PV park")],
        )
        wind = FakeDevice(
            {"Name": "WIND_A", "LibType": "WF_TEMPLATE"},
            [child("Wind mask", "WECC Wind park")],
        )
        bess = FakeDevice(
            {"Name": "BESS_A", "LibType": "BESS_TEMPLATE"},
            [child("BESS mask", "AC-DC converter with control")],
        )
        der = FakeDevice(
            {"Name": "DER_A", "LibType": "DER_TEMPLATE"},
            [child("DER mask", "WECC PV park")],
        )
        synchronous = FakeDevice(
            {"Name": "SG_A", "LibType": "SG_TEMPLATE"},
            [
                child("Machine", "Synchronous machine", "SM"),
                child("LF", "Load-Flow Bus"),
                child("TR_main", "Transformer"),
            ],
        )

        devices = GenerationDeviceCatalog(
            FakeEmtpObject([pv, wind, bess, der, synchronous])
        ).discover()

        self.assertEqual([device.kind for device in devices], list(GenerationKind))
        self.assertEqual(devices[0].template_name, "PV_A")
        self.assertEqual(devices[4].internal_model_path, "SG_A/Machine")

        masks = OperationalScenarioManager(
            FakeEmtpObject([pv, wind, bess, der, synchronous])
        ).discover_generation_masks()
        self.assertEqual(masks[0].mask_host_name, "PV_A")
        self.assertEqual(masks[0].mask_attribute, "XMLDataGrids")

        values = OperationalScenarioManager(
            FakeEmtpObject([pv])
        ).load_generation_values()
        self.assertEqual(
            [(value.parameter, value.value) for value in values],
            [("in_service", "1"), ("p_setpoint", "125.5"), ("q_setpoint", "-3.0")],
        )

        scenario_manager = OperationalScenarioManager(FakeEmtpObject([pv]))
        record = scenario_manager.load_generation_records()[0]
        scenario_manager.apply_generation_changes(
            [
                OperationalScenarioChange(
                    record=record,
                    parameter_values={"p_setpoint": "130.24"},
                    zone="North",
                )
            ]
        )
        self.assertEqual(pv.getAttribute("Zone"), "North")
        self.assertIn("<cell>130.2</cell>", pv.getAttribute("XMLDataGrids"))
        self.assertTrue(
            pv.getAttribute("XMLDataGrids").endswith(
                "<XMLStringSeparator>untouched-grid"
            )
        )

    def test_ignores_templates_that_do_not_have_the_expected_mask(self) -> None:
        incomplete_pv = FakeDevice({"Name": "PV_A", "LibType": "PV_TEMPLATE"})
        incomplete_sg = FakeDevice(
            {"Name": "SG_A", "LibType": "SG_TEMPLATE"},
            [child("Machine", "Synchronous machine", "SM")],
        )

        devices = GenerationDeviceCatalog(
            FakeEmtpObject([incomplete_pv, incomplete_sg])
        ).discover()

        self.assertEqual(devices, [])
