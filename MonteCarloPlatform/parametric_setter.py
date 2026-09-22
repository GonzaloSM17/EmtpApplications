from dataclasses import dataclass, field
from pathlib import Path
from shutil import copy2

from com_client import *
from emtp_utils import *

from config import *
from parametric_calculating import *
from parametric_selecting import *


@dataclass
class SourceModelFile:

    ecf_dir_path: Path  # <- antes se llamaba "ecf_path", ahora es la carpeta
    receptor_path: Path
    ecf_source_name: str  # <- debe incluir la extensión, ej "SEN2026_v0.5.ecf"

    run_files: dict[int, Path] = field(
        default_factory=dict,
        init=False,
    )

    @property
    def ecf_path(self) -> Path:
        """Ruta completa al archivo fuente (carpeta + nombre)."""
        return self.ecf_dir_path / self.ecf_source_name

    def __post_init__(self) -> None:
        self.ecf_dir_path = Path(self.ecf_dir_path)
        self.receptor_path = Path(self.receptor_path)

        if not self.ecf_path.is_file():
            raise FileNotFoundError(f"Source model file not found: {self.ecf_path}")

        self.receptor_path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def create_run_copy(
        self,
        run_id: int,
        overwrite: bool = False,
    ) -> Path:
        run_path = self.receptor_path / (
            f"{self.ecf_path.stem}_run_{run_id:06d}" f"{self.ecf_path.suffix}"
        )

        if run_path.exists() and not overwrite:
            raise FileExistsError(f"Run file already exists: {run_path}")

        copy2(self.ecf_path, run_path)

        self.run_files[run_id] = run_path

        return run_path


class ParameterRun:

    def __init__(self):
        pass


class ParametricRunner:

    def __init__(
        self,
        emtp_object,
        source_model_file: SourceModelFile,
        # paramater_run: Param
    ) -> None:

        self.emtp_object = emtp_object
        self.source_model_file = source_model_file
        self.parameter_assignment = None

        # Open EMTP

    def _back_up_run(self):
        self.source_model_file.create_run_copy(
            run_id=0, overwrite=False
        )  # <- antes usaba variable global

    # def execute(self) -> None:
    #     for parameter_run in self.parameter_assignment.runs:
    #         self._execute_run(parameter_run)

    # def _execute_run(
    #     self,
    #     parameter_run: ParameterRun,
    # ) -> None:
    #     run_path = self.source_model_file.create_run_copy(
    #         run_id=parameter_run.run_id,
    #     )


if __name__ == "__main__":

    # --------------------------------------------------------------
    # Path
    # --------------------------------------------------------------

    source_root = SOURCE_ROOT
    project_root = PROJECT_ROOT

    ecf_source = source_root / "05. Modelos Eléctricos EMTP"
    ecf_receptor = project_root / "temp"

    # --------------------------------------------------------------
    # File Model
    # --------------------------------------------------------------
    source_model_file = SourceModelFile(
        ecf_dir_path=ecf_source,
        receptor_path=ecf_receptor,
        ecf_source_name="SEN2026_v0.5.ecf",
    )

    print(source_model_file.ecf_path)

    # --------------------------------------------------------------
    # EMTP connection
    # --------------------------------------------------------------
    # emtp_client = EmtpComClient(attach_existing=True)
    # emtp_object = emtp_client.emtp_object

    # parametric = ParametricRunner(
    #     emtp_object=emtp_object, source_model_file=source_model_file
    # )
