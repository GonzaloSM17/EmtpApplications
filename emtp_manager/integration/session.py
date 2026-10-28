"""Small, explicit lifecycle wrapper around the existing COM client."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from emtp_manager.integration.com_client import EmtpComClient


class EmtpSession:
    """Own one EMTP connection and open designs through that connection.

    This class is intentionally narrow.  Tkinter and future workflows use it
    instead of reaching into ``com_client`` directly.
    """

    def __init__(
        self,
        client_factory: Callable[[], EmtpComClient] = EmtpComClient,
    ) -> None:
        self._client_factory = client_factory
        self._client: EmtpComClient | None = None
        self.design_path: Path | None = None

    @property
    def emtp_object(self) -> Any:
        if self._client is None:
            raise RuntimeError("EMTP is not connected.")
        return self._client.emtp_object

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def open_design(self, path: str | Path) -> Path:
        """Launch EMTP when needed and open an existing ECF design."""
        design_path = Path(path).expanduser().resolve()
        if not design_path.is_file():
            raise FileNotFoundError(f"EMTP design not found: {design_path}")
        if design_path.suffix.lower() != ".ecf":
            raise ValueError(f"Expected an .ecf design, got: {design_path.name}")

        if self._client is None:
            self._client = self._client_factory()

        self.emtp_object.openDesign(str(design_path))
        self.design_path = design_path
        return design_path

    def save_design(self) -> Path:
        """Persist the currently open working design through the EMTP COM API."""
        if self._client is None or self.design_path is None:
            raise RuntimeError("No EMTP design is open to save.")
        self.emtp_object.saveDesign()
        return self.design_path

    def disconnect(self) -> None:
        """Close the EMTP session explicitly when the caller requests it."""
        if self._client is not None:
            self._client.disconnect()
            self._client = None
            self.design_path = None
