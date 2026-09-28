"""Result emitted by a worker after one lifecycle attempt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WorkerResult:
    execution_id: str
    study_id: str
    run_id: int
    state: str
    started_at: datetime
    finished_at: datetime
    artifacts: dict[str, str]
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "study_id": self.study_id,
            "run_id": self.run_id,
            "state": self.state,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": self.finished_at.isoformat(timespec="seconds"),
            "artifacts": self.artifacts,
            "error": self.error,
        }
