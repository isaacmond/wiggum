"""Stage model representing a single implementation stage."""

from dataclasses import dataclass, field
from enum import Enum


class StageStatus(Enum):
    """Status of a stage in the implementation plan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Stage:
    """Represents a single stage in the implementation plan."""

    number: int
    title: str
    branch: str
    parallel_group: str
    description: str
    status: StageStatus = StageStatus.PENDING
    depends_on: str | None = None
    pr_number: int | None = None
    files: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Stage:
        """Create a Stage from a dictionary."""
        status_str = str(data.get("status", "pending"))
        status = StageStatus(status_str)

        files_raw = data.get("files", [])
        files = list(files_raw) if isinstance(files_raw, list) else []

        criteria_raw = data.get("acceptance_criteria", [])
        criteria = list(criteria_raw) if isinstance(criteria_raw, list) else []

        depends_on_raw = data.get("depends_on")
        depends_on = str(depends_on_raw) if depends_on_raw is not None else None

        pr_number_raw = data.get("pr_number")
        pr_number = int(str(pr_number_raw)) if pr_number_raw is not None else None

        number_raw = data.get("number", 0)
        return cls(
            number=int(str(number_raw)),
            title=str(data.get("title", "")),
            branch=str(data.get("branch", "")),
            parallel_group=str(data.get("parallel_group", "sequential")),
            description=str(data.get("description", "")),
            status=status,
            depends_on=depends_on,
            pr_number=pr_number,
            files=[str(f) for f in files],
            acceptance_criteria=[str(c) for c in criteria],
        )

    def to_dict(self) -> dict[str, object]:
        """Convert Stage to a dictionary."""
        return {
            "number": self.number,
            "title": self.title,
            "branch": self.branch,
            "parallel_group": self.parallel_group,
            "description": self.description,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "pr_number": self.pr_number,
            "files": self.files,
            "acceptance_criteria": self.acceptance_criteria,
        }
