from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from emtp_manager.integration.session import EmtpSession


class FakeGlobalObject:
    def __init__(self) -> None:
        self.opened_paths: list[str] = []

    def openDesign(self, path: str) -> None:
        self.opened_paths.append(path)


class FakeClient:
    def __init__(self) -> None:
        self.emtp_object = FakeGlobalObject()
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class EmtpSessionTests(unittest.TestCase):
    def test_open_design_launches_a_client_once_and_opens_the_ecf(self) -> None:
        clients: list[FakeClient] = []

        def create_client() -> FakeClient:
            client = FakeClient()
            clients.append(client)
            return client

        with TemporaryDirectory() as temporary_directory:
            design_path = Path(temporary_directory) / "network.ecf"
            design_path.touch()

            session = EmtpSession(client_factory=create_client)
            opened_path = session.open_design(design_path)

        self.assertEqual(opened_path.name, "network.ecf")
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].emtp_object.opened_paths, [str(opened_path)])

    def test_open_design_rejects_non_ecf_files_before_creating_emtp(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            design_path = Path(temporary_directory) / "network.txt"
            design_path.touch()

            session = EmtpSession(client_factory=FakeClient)

            with self.assertRaises(ValueError):
                session.open_design(design_path)

        self.assertFalse(session.is_connected)


if __name__ == "__main__":
    unittest.main()
