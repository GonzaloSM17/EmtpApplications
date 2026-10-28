import unittest

from emtp_manager.devices.generation import (
    FormDataFormatError,
    FormDataReader,
    GenerationDevice,
    GenerationKind,
    GenerationSummaryReader,
    BessParameterReader,
    PhotovoltaicParameterReader,
    SynchronousParameterReader,
)


class FakeDevice:
    def __init__(self, attributes: dict[str, str]) -> None:
        self._attributes = attributes

    def getAttribute(self, name: str) -> str:
        return self._attributes.get(name, "")


class FormDataReaderTests(unittest.TestCase):
    def test_reads_xml_form_data_from_photovoltaic_unit_object(self) -> None:
        unit_object = FakeDevice(
            {
                "Name": "PV Park Internal",
                "FormData": (
                    '<Parameters><Ngen value="12"/><Sgen value="4.5"/>'
                    '<QC_select value="2"/><converterModel value="REGC_A"/></Parameters>'
                ),
            }
        )
        device = GenerationDevice(
            kind=GenerationKind.PHOTOVOLTAIC,
            template_name="PV Template",
            template_lib_type="PV_TEMPLATE",
            internal_model_name="PV Park Internal",
            internal_model_lib_type="WECC PV park",
            object=FakeDevice({"Name": "PV Template", "Zone": "North"}),
            unit_object=unit_object,
        )

        parameters = PhotovoltaicParameterReader().read(device)

        self.assertEqual(parameters.snapshot.unit_name, "PV Park Internal")
        self.assertEqual(parameters.snapshot.value_for("Ngen"), "12")
        self.assertEqual(
            [(parameter.key, parameter.value) for parameter in parameters.summary_parameters],
            [("Ngen", "12"), ("Sgen", "4.5"), ("QC_select", "2"), ("converterModel", "REGC_A")],
        )

    def test_rejects_non_xml_form_data_without_writing(self) -> None:
        with self.assertRaises(FormDataFormatError):
            FormDataReader.parse("Ngen,12,Sgen,4.5")

    def test_calculates_verified_aggregate_capacity_in_mva(self) -> None:
        unit_object = FakeDevice(
            {
                "Name": "Wind Park Internal",
                "FormData": (
                    '<Parameters><Ngen value="45"/><Sgen value="1667"/>'
                    '<Sgen_unit value="kVA"/></Parameters>'
                ),
            }
        )
        device = GenerationDevice(
            kind=GenerationKind.WIND,
            template_name="Wind Template",
            template_lib_type="WF_TEMPLATE",
            internal_model_name="Wind Park Internal",
            internal_model_lib_type="WECC Wind park",
            object=FakeDevice({"Name": "Wind Template"}),
            unit_object=unit_object,
        )

        summary = GenerationSummaryReader().read(device)

        self.assertAlmostEqual(summary.capacity_mva or 0, 75.015)
        self.assertEqual(summary.capacity_source, "FormData: Ngen * Sgen")

    def test_reads_bess_inverter_xml_form_data(self) -> None:
        device = GenerationDevice(
            kind=GenerationKind.BESS,
            template_name="BESS Template",
            template_lib_type="BESS_TEMPLATE",
            internal_model_name="BESS Inverter",
            internal_model_lib_type="AC-DC converter with control",
            object=FakeDevice({"Name": "BESS Template"}),
            unit_object=FakeDevice(
                {
                    "Name": "BESS Inverter",
                    "FormData": (
                        '<Parameters><Ngen value="2"/><Sgen value="10"/>'
                        '<Sgen_unit value="MVA"/><converterModel value="Average"/>'
                        '</Parameters>'
                    ),
                }
            ),
        )

        parameters = BessParameterReader().read(device)
        summary = GenerationSummaryReader().read(device)

        self.assertEqual(parameters.all_parameters[0].source, "FormData")
        self.assertEqual(parameters.summary_parameters[0].key, "Ngen")
        self.assertEqual(summary.capacity_mva, 20)

    def test_reads_synchronous_tagged_form_and_model_data(self) -> None:
        device = GenerationDevice(
            kind=GenerationKind.SYNCHRONOUS,
            template_name="SG Template",
            template_lib_type="SG_TEMPLATE",
            internal_model_name="Machine",
            internal_model_lib_type="Synchronous machine",
            object=FakeDevice({"Name": "SG Template"}),
            unit_object=FakeDevice(
                {
                    "Name": "Machine",
                    "FormData": "Ra=0.01 0.15 0.1,\n",
                    "ModelData": "R=13.8 250 1,\nMS=0 Machine 1 1 0,\nMSu=1 0 0,\n",
                }
            ),
        )

        parameters = SynchronousParameterReader().read(device)

        self.assertEqual(
            [(parameter.key, parameter.source) for parameter in parameters.summary_parameters],
            [("R", "ModelData"), ("MS", "ModelData"), ("MSu", "ModelData")],
        )
