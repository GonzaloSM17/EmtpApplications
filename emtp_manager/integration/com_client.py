"""Official EMTP COM client, ported from the EmtpMonteCarlo platform.

The launch/ownership logic is intentionally kept equivalent to MonteCarlo's
client.  The only adaptation is the relative import of its local error type.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
import re
from time import monotonic, sleep
from typing import Any, Callable

import psutil
import pywintypes
import win32api
import win32com.client as win32
import win32con
import win32event
import win32gui
import win32process
import win32ts

from .emtp_errors import EmtpLaunchError


LOGGER = logging.getLogger(__name__)
LAUNCH_MUTEX_NAME = r"Local\EmtpMonteCarloLaunch"


@contextmanager
def _launch_lock():
    """Serialize PID discovery across processes in the current Windows session."""
    handle = win32event.CreateMutex(None, False, LAUNCH_MUTEX_NAME)
    acquired = False
    try:
        result = win32event.WaitForSingleObject(handle, 300_000)
        if result not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
            raise TimeoutError("Timed out waiting to launch an EMTPWorks instance.")
        acquired = True
        yield
    finally:
        if acquired:
            win32event.ReleaseMutex(handle)
        win32api.CloseHandle(handle)


def _emtp_process_ids(session_id: int) -> set[int]:
    """Find EMTP GUI processes only in the worker's Windows session."""
    result: set[int] = set()
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = str(process.info.get("name") or "").casefold()
            if re.fullmatch(r"emtpworks\d+\.exe", name):
                process_session_id = win32ts.ProcessIdToSessionId(process.pid)
                if process_session_id == session_id:
                    result.add(process.pid)
                else:
                    LOGGER.debug(
                        "Ignoring EMTPWorks PID %s in Windows session %s (worker session %s).",
                        process.pid,
                        process_session_id,
                        session_id,
                    )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except pywintypes.error as exc:
            LOGGER.debug(
                "Cannot determine Windows session for EMTPWorks PID %s; ignoring: %s",
                process.pid,
                exc,
            )
    return result


def _request_window_close(pid: int) -> int:
    """Ask only top-level windows owned by this EMTP PID to close."""
    windows: list[int] = []

    def collect(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        _thread_id, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
        if owner_pid == pid:
            windows.append(hwnd)

    win32gui.EnumWindows(collect, None)
    for hwnd in windows:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    return len(windows)


@dataclass
class EmtpComClient:
    """Own a new EMTP instance or safely attach to an existing one."""

    program_id: str = "EMTPWorks460.Application.Single"
    _app_emtp: Any = None
    _emtp_object: Any = None
    _owned_process: psutil.Process | None = None
    visible: bool = True
    on_process_started: Callable[[psutil.Process, int], None] | None = None
    on_launch_state: Callable[..., None] | None = None
    attach_existing: bool = False

    def __post_init__(self) -> None:
        self.connect()

    def connect(self) -> Any:
        if self.attach_existing:
            self._connect_existing()
        else:
            self._connect_new()
        if self._emtp_object is None:
            self.disconnect()
            raise RuntimeError("Failed to obtain globalObject.")
        return self._emtp_object

    def _connect_existing(self) -> None:
        existing_program_id = "EMTPWorks460.Application"
        try:
            self._app_emtp = win32.Dispatch(existing_program_id)
        except Exception as exc:
            raise RuntimeError(
                f"Could not attach to a running EMTP instance ('{existing_program_id}'). "
                "Make sure EMTPWorks is open before connecting."
            ) from exc
        self._app_emtp.ShowHide(self.visible)
        self._emtp_object = self._app_emtp.getGlobalObject

    def _connect_new(self) -> None:
        self._launch_state("waiting")
        worker_pid = os.getpid()
        try:
            session_id = win32ts.ProcessIdToSessionId(worker_pid)
        except pywintypes.error as exc:
            self._launch_state("failed")
            raise EmtpLaunchError(
                f"Cannot determine Windows session for worker PID {worker_pid}."
            ) from exc
        with _launch_lock():
            before = _emtp_process_ids(session_id)
            LOGGER.info(
                "Launching EMTPWorks for worker PID %s in Windows session %s; existing PIDs: %s.",
                worker_pid,
                session_id,
                sorted(before),
            )
            self._launch_state("requested")
            try:
                self._app_emtp = win32.DispatchEx(self.program_id)
            except Exception as error:
                candidates = _emtp_process_ids(session_id) - before
                if len(candidates) == 1:
                    self._register_process(candidates.pop(), session_id)
                elif not candidates:
                    self._launch_state("no_process")
                self._launch_state("failed")
                raise EmtpLaunchError(f"EMTP COM activation failed: {error}") from error
            new_pids = _emtp_process_ids(session_id) - before
            if len(new_pids) != 1:
                self._app_emtp = self._emtp_object = None
                self._launch_state("failed")
                raise EmtpLaunchError(
                    "Cannot identify one owned EMTPWorks process after launch; "
                    f"found {len(new_pids)} new processes in Windows session {session_id} "
                    f"(worker PID {worker_pid}, candidate PIDs: {sorted(new_pids)})."
                )
            pid = new_pids.pop()
            self._register_process(pid, session_id)
            try:
                self._app_emtp.ShowHide(self.visible)
                self._emtp_object = self._app_emtp.getGlobalObject
                if self._emtp_object is None:
                    raise RuntimeError("Failed to obtain globalObject.")
            except Exception as error:
                self._launch_state("failed")
                raise EmtpLaunchError(f"EMTP COM initialization failed: {error}") from error
        LOGGER.info("Started owned EMTPWorks process PID %s in Windows session %s.", pid, session_id)

    def _launch_state(self, state: str) -> None:
        if self.on_launch_state is not None:
            self.on_launch_state(state)

    def _register_process(self, pid: int, session_id: int) -> None:
        self._owned_process = psutil.Process(pid)
        self._owned_process.create_time()
        if self.on_process_started is not None:
            self.on_process_started(self._owned_process, session_id)

    def disconnect(self) -> bool:
        if self._app_emtp is None:
            raise RuntimeError("No active connection to disconnect.")
        process = self._owned_process
        self._app_emtp = self._emtp_object = None
        self._owned_process = None
        if process is None:
            return True
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        except psutil.NoSuchProcess:
            return True
        except psutil.AccessDenied:
            try:
                windows = _request_window_close(process.pid)
                deadline = monotonic() + 5.0
                while process.is_running() and monotonic() < deadline:
                    sleep(0.2)
                if not process.is_running():
                    LOGGER.info("Owned EMTPWorks PID %s has exited.", process.pid)
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as error:
                LOGGER.warning("Could not close EMTPWorks PID %s window: %s", process.pid, error)
                windows = 0
            LOGGER.warning(
                "Windows denied termination of owned EMTPWorks PID %s; "
                "%s window(s) received a close request, but the process may remain open.",
                process.pid,
                windows,
            )
            return False
        LOGGER.info("Stopped owned EMTPWorks process PID %s.", process.pid)
        return True

    @property
    def emtp_object(self) -> Any:
        """GlobalObject -- top-level COM context for this EMTP instance."""
        if self._emtp_object is None:
            raise RuntimeError("Not connected.")
        return self._emtp_object
