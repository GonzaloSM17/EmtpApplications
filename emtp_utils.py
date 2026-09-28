from __future__ import annotations

import json
import time
from typing import Any
from pathlib import Path

import tkinter as tk
from tkinter import filedialog

# ----------------------------------------------------------------------
# Utils — pure static helpers, no state
# ----------------------------------------------------------------------


class Utils:

    @staticmethod
    def parse_script_file(emtp_object: Any, script_path: str) -> None:
        psf_disp_id = 1165
        emtp_object._oleobj_.Invoke(psf_disp_id, 0, 1, 1, script_path)

    @staticmethod
    def set_params_from_dict(
        emtp_object: Any, device_name: str, params: dict[str, Any]
    ) -> None:
        # print("set " + str(newParamsDict))
        js_data = json.dumps(params)
        # print("New jsData: " + jsData)
        # Using global values to pass arguments as we have no way to call
        # methods inside EMTPWorks directly
        # These names must match those used in the param access script in EW
        emtp_object.setGlobalValue("_ext_param_dev_name_", device_name)
        emtp_object.setGlobalValue("_ext_param_dev_operation_", "put")
        emtp_object.setGlobalValue("_ext_param_dev_data_", js_data)
        emtp_object.parseScriptFile("external_get_set_device_params.dwj")

    @staticmethod
    def get_object_from_array(array: Any, index: int) -> Any:
        index_str = str(index)
        invkind, dispid = array._find_dispatch_type_(index_str)
        return array._get_good_object_(array._oleobj_.Invoke(dispid, 0, invkind, 1))

    @staticmethod
    def get_params_to_dict(
        emtp_object: Any,
        device_name: str,
    ) -> dict[str, Any]:
        emtp_object.setGlobalValue("_ext_param_dev_name_", device_name)
        emtp_object.setGlobalValue("_ext_param_dev_operation_", "get")

        results = emtp_object.parseScriptFile("external_get_set_device_params.dwj")

        if not isinstance(results, str):
            raise RuntimeError(
                f"Expected string response for device {device_name}, got {type(results)}: {results}"
            )

        if results.startswith("***"):
            raise RuntimeError(
                f"Getting parameters for {device_name} failed: {results}"
            )

        return json.loads(results)

    @classmethod
    def get_params_to_dict_by_path(
        cls,
        emtp_object: Any,
        device_path: str,
    ) -> dict[str, Any]:
        script_path = (
            Path(__file__).resolve().parent
            / "js_scripts"
            / "external_get_set_device_params_by_path.dwj"
        )

        emtp_object.setGlobalValue("_ext_param_dev_path_", device_path)
        emtp_object.setGlobalValue("_ext_param_dev_operation_", "get")

        result = emtp_object.parseScriptFile(str(script_path))

        if not isinstance(result, str):
            raise RuntimeError(
                f"Expected string response for device path {device_path}, "
                f"got {type(result)}: {result}"
            )

        if result.startswith("***"):
            raise RuntimeError(result)

        return json.loads(result)

    @classmethod
    def set_params_from_dict_by_path(
        cls,
        emtp_object: Any,
        device_path: str,
        params: dict[str, Any],
    ) -> None:
        script_path = (
            Path(__file__).resolve().parent
            / "js_scripts"
            / "external_get_set_device_params_by_path.dwj"
        )

        js_data = json.dumps(params)

        emtp_object.setGlobalValue("_ext_param_dev_path_", device_path)
        emtp_object.setGlobalValue("_ext_param_dev_operation_", "put")
        emtp_object.setGlobalValue("_ext_param_dev_data_", js_data)

        result = emtp_object.parseScriptFile(str(script_path))

        if isinstance(result, str) and result.startswith("***"):
            raise RuntimeError(result)

        if isinstance(result, str) and result != "OK":
            raise RuntimeError(
                f"Unexpected response while setting parameters for {device_path}: {result}"
            )


# ----------------------------------------------------------------------
# Context — shared accessors, re-evaluated on every call
# ----------------------------------------------------------------------


class Context:

    @classmethod
    def design(cls, emtp_object: Any) -> Any:
        design = emtp_object.currentDesign
        if design is None:
            raise RuntimeError("No design is currently open.")
        return design

    @classmethod
    def circuit(cls, emtp_object: Any) -> Any:
        circuit = emtp_object.currentCircuit
        if circuit is None:
            raise RuntimeError("No circuit is currently open.")
        return circuit

    @classmethod
    def devices(cls, emtp_object: Any) -> Any:
        devices = cls.design(emtp_object).devices
        if devices is None:
            raise RuntimeError("No devices are currently in the design.")
        return devices

    @classmethod
    def signals(cls, emtp_object: Any) -> Any:
        signals = cls.design(emtp_object).signals
        if signals is None:
            raise RuntimeError("No signals are currently in the design.")
        return signals


# ----------------------------------------------------------------------
# Design
# ----------------------------------------------------------------------


class Design(Context):

    @staticmethod
    def _select_ecf() -> str | None:
        root = tk.Tk()
        root.withdraw()

        path = filedialog.askopenfilename(
            title="Seleccionar diseño EMTP",
            filetypes=[("EMTP Design", "*.ecf")],
        )

        # root.destroy()

        return path if path else None

    @classmethod
    def open_design(
        cls,
        emtp_object: Any,
        path: str | None = None,
    ) -> None:

        if path is None or not Path(path).exists():
            path = cls._select_ecf()

        if not path:
            return

        emtp_object.openDesign(path)

    @classmethod
    def save(cls, emtp_object: Any, path: str | None = None) -> None:
        design = cls.design(emtp_object)
        if design:
            if path is not None:
                design.saveAs(path)
            else:
                design.save

    @classmethod
    def save_copy(cls, emtp_object: Any, path: str | None = None) -> None:
        design = cls.design(emtp_object)
        if design:
            design.saveCopy(path)

    @classmethod
    def close_design(cls, emtp_object: Any, save_path: str | None = None) -> None:
        if save_path is not None:
            cls.save(emtp_object, save_path)
        cls.design(emtp_object).close


# ----------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------


class Simulation(Context):

    @classmethod
    def run_load_flow(
        cls,
        emtp_object: Any,
        default_frequency: int = 50,
        poll_s: float = 1.0,
    ) -> Any:
        Utils.set_params_from_dict(
            emtp_object,
            "SIMOPT",
            {
                "LoadFlow": "1",
                "Start_LF_from_LF": "0",
                "fscan": "0",
                "DefaultFrequency": str(default_frequency),
            },
        )

        status = cls.design(emtp_object).runSimulation("lf", 2)

        while not status.resultsAvailable:
            time.sleep(poll_s)

        return status

    @classmethod
    def run_time_domain(
        cls,
        emtp_object: Any,
        Dt: int = 50,
        Dtu: str = "us",
        tmax: float = 10.0,
        tmaxu: str = "",
        default_frequency: int = 50,
        poll_s: float = 1.0,
    ) -> Any:
        Utils.set_params_from_dict(
            emtp_object,
            "SIMOPT",
            {
                "LoadFlow": "0",
                "steadystate": "1",
                "StartFromLoadFlow": "1",
                "timedomain": "1",
                "Dt": str(Dt),
                "Dtu": Dtu,
                "tmax": str(tmax),
                "tmaxu": tmaxu,
                "fscan": "0",
                "DefaultFrequency": str(default_frequency),
            },
        )

        status = cls.circuit(emtp_object).runSimulation("td", 2)

        while not status.resultsAvailable:
            time.sleep(poll_s)

        return status


# ----------------------------------------------------------------------
# Finder
# ----------------------------------------------------------------------


class Finder(Context):

    @classmethod
    def find_device(cls, emtp_object: Any, name: str) -> Any:
        devices = cls.devices(emtp_object)

        for i in range(devices.length):
            obj = Utils.get_object_from_array(devices, i)
            if obj is not None and getattr(obj, "name", None) == name:
                return obj

        return None

    @classmethod
    def find_signal(cls, emtp_object: Any, name: str) -> Any:
        design = cls.design(emtp_object)
        locator = design.getSignalLocatorByName(name)

        if not locator:
            raise RuntimeError(f"Signal not found: {name}")

        obj = design.findByLocator(locator)
        if obj is None:
            return None

        return obj

    @classmethod
    def find_pin(cls, device: Any, name: str) -> Any:
        pins = device.pins

        for i in range(pins.length):
            pin = Utils.get_object_from_array(pins, i)

            if pin is not None and getattr(pin, "name", None) == name:
                return pin

        return None

    @classmethod
    def find_device_in(cls, circuit: Any, name: str) -> Any:
        devices = circuit.devices

        for i in range(devices.length):
            device = Utils.get_object_from_array(devices, i)

            if device is not None and getattr(device, "name", None) == name:
                return device

        return None


# ----------------------------------------------------------------------
# Device
# ----------------------------------------------------------------------


class Device(Context):

    @classmethod
    def find_device(cls, emtp_object: Any, name: str) -> Any:
        return Finder.find_device(emtp_object, name)

    @classmethod
    def set_params_from_dict(
        cls, emtp_object: Any, device: Any | str, params: dict[str, Any]
    ) -> None:

        if isinstance(device, str):
            device = cls.find_device(emtp_object, device)
        name = device.name
        Utils.set_params_from_dict(emtp_object, name, params)

    @classmethod
    def get_params_to_dict(cls, emtp_object: Any, device: Any | str) -> dict[str, Any]:

        if isinstance(device, str):
            device = cls.find_device(emtp_object, device)

        name = device.name
        return Utils.get_params_to_dict(emtp_object, name)

    @classmethod
    def exclude_device(cls, emtp_object: Any, device: Any | str) -> None:
        if isinstance(device, str):
            device = cls.find_device(emtp_object, device)

        status = device.getAttribute("Exclude")
        if status.length == 0:
            device.setAttribute("Exclude", "Ex")

    @classmethod
    def include_device(cls, emtp_object: Any, device: Any | str) -> None:
        if isinstance(device, str):
            device = cls.find_device(emtp_object, device)

        status = device.getAttribute("Exclude")
        if status != 2:
            device.setAttribute("Exclude", "")


# ----------------------------------------------------------------------
# Library
# ----------------------------------------------------------------------


class Library(Context):

    @classmethod
    def open_library(cls, emtp_object: Any, library_path: str = None) -> None:

        if library_path is None:
            raise ValueError("Library path is required.")

        emtp_object.openLibrary(library_path, True)

    @classmethod
    def find_library(cls, emtp_object: Any, name: str) -> Any:
        libraries = emtp_object.libraryList

        for i in range(libraries.length):
            library = Utils.get_object_from_array(libraries, i)

            if library is not None and getattr(library, "name", None) == name:
                return library

        raise RuntimeError(f"Library not found: {name}")

    @classmethod
    def find_type(cls, emtp_object: Any, library_name: str, type_name: str) -> Any:
        library = cls.find_library(emtp_object, library_name)
        types = library.typeList

        for i in range(types.length):
            type = Utils.get_object_from_array(types, i)

            if type is not None and getattr(type, "name", None) == type_name:
                return type

        raise RuntimeError(f"Type not found: {library_name} / {type_name}")


if __name__ == "__main__":

    from com_client import EmtpComClient

    # emtp_client = EmtpComClient()
    # emtp_object = emtp_client.emtp_object
