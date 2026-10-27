"""Import and catalogue EMTP projects in a managed local workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid


WORKSPACE_ENV_VAR = "EMTP_DATA_MANAGER_HOME"
DEFAULT_WORKSPACE_ROOT = Path(r"C:\EMTPDataManager")
MANIFEST_NAME = "project.json"


class WorkspaceError(RuntimeError):
    """A project cannot be safely managed in the local workspace."""


@dataclass(frozen=True)
class ManagedProject:
    """Persistent project identity and its immutable/working copies."""

    id: str
    name: str
    description: str
    source_root: str
    design_relative_path: str
    imported_at: str
    last_opened_at: str | None = None
    source_design_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ManagedProject":
        required = {"id", "name", "source_root", "design_relative_path", "imported_at"}
        missing = required.difference(data)
        if missing:
            raise WorkspaceError(
                f"Project manifest is missing field(s): {', '.join(sorted(missing))}"
            )
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            description=str(data.get("description") or ""),
            source_root=str(data["source_root"]),
            design_relative_path=str(data["design_relative_path"]),
            imported_at=str(data["imported_at"]),
            last_opened_at=(
                str(data["last_opened_at"])
                if data.get("last_opened_at") is not None
                else None
            ),
            source_design_path=(
                str(data["source_design_path"])
                if data.get("source_design_path") is not None
                else None
            ),
        )


class WorkspaceManager:
    """Own durable project copies and temporary execution space.

    Source projects are never opened or changed by this class. A normal import
    copies only the selected ECF to ``baseline``; EMTP always receives
    ``working`` instead. Supporting files must be imported explicitly later.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        configured_root = root or os.environ.get(WORKSPACE_ENV_VAR)
        self.root = Path(configured_root or DEFAULT_WORKSPACE_ROOT).expanduser()

    @property
    def projects_root(self) -> Path:
        return self.root / "projects"

    @property
    def archive_root(self) -> Path:
        return self.root / "archive"

    def initialize(self) -> None:
        """Create only the folder structure required by the application."""
        for directory in (
            self.root,
            self.projects_root,
            self.archive_root,
            self.root / "app",
            self.root / "app" / "logs",
            self.root / "runtime",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[ManagedProject]:
        """Read valid project manifests without starting EMTP."""
        self.initialize()
        projects: list[ManagedProject] = []
        for manifest_path in self.projects_root.glob(f"*/{MANIFEST_NAME}"):
            try:
                projects.append(self._read_manifest(manifest_path))
            except (OSError, json.JSONDecodeError, WorkspaceError):
                # A damaged project must not prevent the overview from loading.
                continue
        return sorted(projects, key=lambda project: project.name.casefold())

    def import_design(self, design_path: str | Path) -> ManagedProject:
        """Import only an ECF file and return its managed project metadata."""
        source_design = Path(design_path).expanduser().resolve()
        if not source_design.is_file():
            raise FileNotFoundError(f"EMTP design not found: {source_design}")
        if source_design.suffix.lower() != ".ecf":
            raise ValueError(f"Expected an .ecf design, got: {source_design.name}")

        self.initialize()
        source_root = source_design.parent
        relative_design_path = Path(source_design.name)
        existing_project = self._find_project_by_source(source_design)
        if existing_project is not None:
            project = existing_project
            self._ensure_working_copy(project)
            return project

        project_id = self._new_project_id()
        project_directory = self.projects_root / project_id

        temporary_directory = self.root / "runtime" / f"import-{project_id}"
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)

        try:
            temporary_directory.mkdir()
            baseline_directory = temporary_directory / "baseline"
            baseline_directory.mkdir()
            shutil.copy2(source_design, baseline_directory / source_design.name)

            working_directory = temporary_directory / "working"
            working_directory.mkdir()
            shutil.copy2(source_design, working_directory / source_design.name)
            (temporary_directory / "runs").mkdir()
            (temporary_directory / "cache").mkdir()

            project = ManagedProject(
                id=project_id,
                name=source_design.stem,
                description="",
                source_root=str(source_root),
                design_relative_path=relative_design_path.as_posix(),
                imported_at=self._timestamp(),
                source_design_path=str(source_design),
            )
            self._write_manifest(temporary_directory / MANIFEST_NAME, project)
            temporary_directory.replace(project_directory)
            return project
        except OSError as exc:
            raise WorkspaceError(
                f"Could not import project into {project_directory}: {exc}"
            ) from exc
        finally:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)

    def working_design_path(self, project: ManagedProject) -> Path:
        """Return the design to open in EMTP and record its access time."""
        self._ensure_working_copy(project)
        design_path = self.project_directory(project) / "working" / project.design_relative_path
        if not design_path.is_file():
            raise WorkspaceError(
                f"Working design is missing for project {project.name!r}: {design_path}"
            )

        opened_project = ManagedProject(
            **{**asdict(project), "last_opened_at": self._timestamp()}
        )
        self._write_manifest(
            self.project_directory(project) / MANIFEST_NAME,
            opened_project,
        )
        return design_path

    def project_directory(self, project: ManagedProject) -> Path:
        return self.projects_root / project.id

    def rename_project(self, project: ManagedProject, name: str) -> ManagedProject:
        """Change the display name without changing project identity or files."""
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Project name cannot be empty.")

        renamed_project = ManagedProject(**{**asdict(project), "name": cleaned_name})
        self._write_manifest(
            self.project_directory(project) / MANIFEST_NAME,
            renamed_project,
        )
        return renamed_project

    def update_description(self, project: ManagedProject, description: str) -> ManagedProject:
        """Store a free-form project note without touching any EMTP files."""
        described_project = ManagedProject(
            **{**asdict(project), "description": description.strip()}
        )
        self._write_manifest(
            self.project_directory(project) / MANIFEST_NAME,
            described_project,
        )
        return described_project

    def rename_design(self, project: ManagedProject, filename: str) -> ManagedProject:
        """Rename the managed ECF in both baseline and working copies.

        A design name is deliberately only a filename.  The workspace controls
        its directory, so a rename cannot move an ECF outside the project or
        silently alter unrelated support files.
        """
        cleaned_name = filename.strip()
        candidate = Path(cleaned_name)
        if not cleaned_name or candidate.name != cleaned_name:
            raise ValueError("The ECF name must be a filename, not a path.")
        if candidate.suffix.lower() != ".ecf":
            raise ValueError("The design name must end in .ecf.")

        old_relative_path = Path(project.design_relative_path)
        if old_relative_path.name != project.design_relative_path:
            raise WorkspaceError("Only top-level managed ECF names can be renamed.")
        if old_relative_path.name == cleaned_name:
            return project

        project_directory = self.project_directory(project)
        source_paths = (
            project_directory / "baseline" / old_relative_path,
            project_directory / "working" / old_relative_path,
        )
        destination_paths = tuple(path.with_name(cleaned_name) for path in source_paths)
        if not source_paths[0].is_file():
            raise WorkspaceError(f"Baseline design is missing: {source_paths[0]}")
        if any(path.exists() for path in destination_paths):
            raise WorkspaceError(f"A managed design named {cleaned_name!r} already exists.")

        renamed_paths: list[tuple[Path, Path]] = []
        try:
            for source, destination in zip(source_paths, destination_paths):
                if source.exists():
                    source.replace(destination)
                    renamed_paths.append((source, destination))
        except OSError as exc:
            for source, destination in reversed(renamed_paths):
                if destination.exists():
                    destination.replace(source)
            raise WorkspaceError(f"Could not rename managed design: {exc}") from exc

        renamed_project = ManagedProject(
            **{**asdict(project), "design_relative_path": cleaned_name}
        )
        self._write_manifest(project_directory / MANIFEST_NAME, renamed_project)
        return renamed_project

    def promote_working_to_baseline(self, project: ManagedProject) -> None:
        """Replace the baseline directory with an exact copy of ``working``.

        This is intentionally a directory-level operation: when future
        workflows add explicit support files, the baseline remains an exact
        managed counterpart of the working state rather than only its ECF.
        """
        project_directory = self.project_directory(project)
        baseline_directory = project_directory / "baseline"
        working_directory = project_directory / "working"
        if not working_directory.is_dir():
            raise WorkspaceError(f"Working copy is missing for project {project.name!r}.")
        if not (working_directory / project.design_relative_path).is_file():
            raise WorkspaceError("The working ECF is missing; baseline was not changed.")

        staging_directory = self.root / "runtime" / f"promote-{project.id}"
        previous_baseline = self.root / "runtime" / f"baseline-backup-{project.id}"
        for directory in (staging_directory, previous_baseline):
            if directory.exists():
                shutil.rmtree(directory)
        try:
            shutil.copytree(working_directory, staging_directory, copy_function=shutil.copy2)
            if baseline_directory.exists():
                baseline_directory.replace(previous_baseline)
            staging_directory.replace(baseline_directory)
        except OSError as exc:
            if not baseline_directory.exists() and previous_baseline.exists():
                previous_baseline.replace(baseline_directory)
            raise WorkspaceError(f"Could not update baseline from working copy: {exc}") from exc
        finally:
            if staging_directory.exists():
                shutil.rmtree(staging_directory)
            if previous_baseline.exists():
                shutil.rmtree(previous_baseline)

    def export_project(
        self,
        project: ManagedProject,
        source: str,
        destination_root: str | Path,
    ) -> Path:
        """Copy either managed version into a new folder selected by the user."""
        if source not in {"baseline", "working"}:
            raise ValueError("Export source must be 'baseline' or 'working'.")
        source_directory = self.project_directory(project) / source
        if not source_directory.is_dir():
            raise WorkspaceError(f"{source.title()} copy is missing for project {project.name!r}.")

        destination_root_path = Path(destination_root).expanduser().resolve()
        if not destination_root_path.is_dir():
            raise NotADirectoryError(f"Export destination is not a folder: {destination_root_path}")
        destination = destination_root_path / f"{project.id}_{source}"
        if destination.exists():
            raise WorkspaceError(
                f"Export destination already exists: {destination}. Choose another folder or rename it first."
            )
        try:
            shutil.copytree(source_directory, destination, copy_function=shutil.copy2)
        except OSError as exc:
            raise WorkspaceError(f"Could not export {source} copy: {exc}") from exc
        return destination

    def clear_cache(self, project: ManagedProject) -> None:
        """Discard only regenerable files belonging to one managed project."""
        cache_directory = self.project_directory(project) / "cache"
        if cache_directory.exists():
            shutil.rmtree(cache_directory)
        cache_directory.mkdir(parents=True)

    def archive_project(self, project: ManagedProject) -> Path:
        """Move a managed project out of the active catalogue without deleting it."""
        project_directory = self.project_directory(project)
        if not project_directory.is_dir():
            raise WorkspaceError(f"Managed project is missing: {project.name!r}.")

        destination = self.archive_root / f"{project.id}-{self._archive_timestamp()}"
        project_directory.replace(destination)
        return destination

    def _ensure_working_copy(self, project: ManagedProject) -> None:
        project_directory = self.project_directory(project)
        baseline_directory = project_directory / "baseline"
        working_directory = project_directory / "working"
        if not baseline_directory.is_dir():
            raise WorkspaceError(f"Baseline is missing for project {project.name!r}.")
        if not working_directory.is_dir():
            shutil.copytree(baseline_directory, working_directory, copy_function=shutil.copy2)

    def _read_manifest(self, manifest_path: Path) -> ManagedProject:
        with manifest_path.open(encoding="utf-8") as manifest_file:
            return ManagedProject.from_dict(json.load(manifest_file))

    def _write_manifest(self, manifest_path: Path, project: ManagedProject) -> None:
        with manifest_path.open("w", encoding="utf-8") as manifest_file:
            json.dump(asdict(project), manifest_file, indent=2, ensure_ascii=False)
            manifest_file.write("\n")

    def _find_project_by_source(self, source_design: Path) -> ManagedProject | None:
        normalized_source = source_design.resolve()
        for project in self.list_projects():
            candidate_source = (
                Path(project.source_design_path)
                if project.source_design_path
                else Path(project.source_root) / project.design_relative_path
            )
            try:
                if candidate_source.resolve() == normalized_source:
                    return project
            except OSError:
                continue
        return None

    @staticmethod
    def _new_project_id() -> str:
        """Generate an opaque filesystem-safe ID, independent of all names."""
        return "p" + uuid.uuid4().hex

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _archive_timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
