from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from emtp_manager.workspace.manager import WorkspaceManager


class WorkspaceManagerTests(unittest.TestCase):
    def test_import_copies_only_the_ecf_and_keeps_the_source_untouched(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.write_text("original design", encoding="utf-8")
            (source_root / "library.dat").write_text("library", encoding="utf-8")

            manager = WorkspaceManager(root / "manager-workspace")
            project = manager.import_design(source_design)
            working_design = manager.working_design_path(project)

            self.assertRegex(project.id, r"^p[a-f0-9]{32}$")
            self.assertNotEqual(working_design, source_design)
            self.assertEqual(working_design.read_text(encoding="utf-8"), "original design")
            self.assertFalse((manager.project_directory(project) / "baseline" / "library.dat").exists())
            self.assertTrue((manager.project_directory(project) / "runs").is_dir())
            self.assertTrue((manager.project_directory(project) / "cache").is_dir())

            working_design.write_text("working change", encoding="utf-8")
            self.assertEqual(source_design.read_text(encoding="utf-8"), "original design")

    def test_existing_import_reuses_the_managed_project(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.touch()

            manager = WorkspaceManager(root / "manager-workspace")
            first_project = manager.import_design(source_design)
            second_project = manager.import_design(source_design)

            self.assertEqual(first_project.id, second_project.id)
            self.assertEqual(len(manager.list_projects()), 1)

    def test_project_name_can_change_without_changing_its_identity_or_design(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.touch()

            manager = WorkspaceManager(root / "manager-workspace")
            project = manager.import_design(source_design)
            renamed_project = manager.rename_project(project, "North Zone PV Study")

            self.assertEqual(renamed_project.id, project.id)
            self.assertEqual(renamed_project.name, "North Zone PV Study")
            self.assertEqual(renamed_project.design_relative_path, "network.ecf")

    def test_description_and_ecf_rename_are_persisted_for_both_managed_copies(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.write_text("source", encoding="utf-8")

            manager = WorkspaceManager(root / "manager-workspace")
            project = manager.import_design(source_design)
            described_project = manager.update_description(project, "Initial fault-level case\nReviewed.")
            renamed_project = manager.rename_design(described_project, "north_zone.ecf")
            project_directory = manager.project_directory(renamed_project)

            self.assertEqual(renamed_project.description, "Initial fault-level case\nReviewed.")
            self.assertEqual(renamed_project.design_relative_path, "north_zone.ecf")
            self.assertTrue((project_directory / "baseline" / "north_zone.ecf").is_file())
            self.assertTrue((project_directory / "working" / "north_zone.ecf").is_file())
            self.assertFalse((project_directory / "baseline" / "network.ecf").exists())
            self.assertEqual(manager.list_projects()[0], renamed_project)

    def test_working_can_replace_baseline_and_each_version_can_be_exported(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.write_text("baseline", encoding="utf-8")

            manager = WorkspaceManager(root / "manager-workspace")
            project = manager.import_design(source_design)
            project_directory = manager.project_directory(project)
            working_design = project_directory / "working" / "network.ecf"
            working_design.write_text("working revision", encoding="utf-8")
            (project_directory / "working" / "explicit-support-file.txt").write_text(
                "support", encoding="utf-8"
            )

            manager.promote_working_to_baseline(project)
            self.assertEqual(
                (project_directory / "baseline" / "network.ecf").read_text(encoding="utf-8"),
                "working revision",
            )
            self.assertTrue((project_directory / "baseline" / "explicit-support-file.txt").is_file())

            export_root = root / "exports"
            export_root.mkdir()
            exported_baseline = manager.export_project(project, "baseline", export_root)
            exported_working = manager.export_project(project, "working", export_root)
            self.assertEqual(
                (exported_baseline / "network.ecf").read_text(encoding="utf-8"),
                "working revision",
            )
            self.assertTrue((exported_working / "explicit-support-file.txt").is_file())

    def test_clear_cache_and_archive_do_not_modify_baseline_or_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source-project"
            source_root.mkdir()
            source_design = source_root / "network.ecf"
            source_design.write_text("original", encoding="utf-8")

            manager = WorkspaceManager(root / "manager-workspace")
            project = manager.import_design(source_design)
            cache_file = manager.project_directory(project) / "cache" / "temporary.out"
            cache_file.write_text("discard me", encoding="utf-8")

            manager.clear_cache(project)
            self.assertFalse(cache_file.exists())

            archive_path = manager.archive_project(project)
            self.assertTrue((archive_path / "baseline" / "network.ecf").is_file())
            self.assertEqual(source_design.read_text(encoding="utf-8"), "original")
            self.assertEqual(manager.list_projects(), [])


if __name__ == "__main__":
    unittest.main()
