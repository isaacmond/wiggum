"""TODO file parser for Smithers implementation plans."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from smithers.exceptions import TodoParseError
from smithers.models.stage import Stage, StageStatus


@dataclass
class TodoFile:
    """Represents a parsed TODO/implementation plan file."""

    path: Path
    title: str
    overview: str
    stages: list[Stage] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def parse(cls, path: Path) -> TodoFile:
        """Parse a TODO file from the given path."""
        if not path.exists():
            raise TodoParseError(f"TODO file not found: {path}")

        content = path.read_text()
        return cls.parse_content(content, path)

    @classmethod
    def parse_content(cls, content: str, path: Path | None = None) -> TodoFile:
        """Parse TODO file content."""
        lines = content.split("\n")

        title = ""
        overview = ""
        notes = ""
        stages: list[Stage] = []

        current_section = ""
        current_stage_data: dict[str, object] = {}
        overview_lines: list[str] = []
        notes_lines: list[str] = []

        for line in lines:
            # Match title: # Implementation Plan: [Title]
            if line.startswith("# "):
                title = line[2:].strip()
                continue

            # Match section headers
            if line.startswith("## Overview"):
                current_section = "overview"
                continue
            if line.startswith("## Stages"):
                current_section = "stages"
                continue
            if line.startswith("## Notes"):
                current_section = "notes"
                continue

            # Match stage header: ### Stage N: Title
            stage_match = re.match(r"^###\s+Stage\s+(\d+):\s*(.+)$", line)
            if stage_match:
                # Save previous stage if exists
                if current_stage_data:
                    stages.append(Stage.from_dict(current_stage_data))

                current_stage_data = {
                    "number": int(stage_match.group(1)),
                    "title": stage_match.group(2).strip(),
                }
                current_section = "stage"
                continue

            # Parse stage fields
            if current_section == "stage":
                current_stage_data = _parse_stage_line(line, current_stage_data)
            elif current_section == "overview":
                overview_lines.append(line)
            elif current_section == "notes":
                notes_lines.append(line)

        # Save last stage
        if current_stage_data:
            stages.append(Stage.from_dict(current_stage_data))

        overview = "\n".join(overview_lines).strip()
        notes = "\n".join(notes_lines).strip()

        return cls(
            path=path or Path("unknown"),
            title=title,
            overview=overview,
            stages=stages,
            notes=notes,
        )

    def get_stages_by_group(self) -> dict[str, list[Stage]]:
        """Get stages organized by parallel group."""
        groups: dict[str, list[Stage]] = {}
        for stage in self.stages:
            group = stage.parallel_group
            if group not in groups:
                groups[group] = []
            groups[group].append(stage)
        return groups

    def get_parallel_groups_in_order(self) -> list[str]:
        """Get unique parallel groups in the order they appear."""
        seen: set[str] = set()
        groups: list[str] = []
        for stage in self.stages:
            if stage.parallel_group not in seen:
                seen.add(stage.parallel_group)
                groups.append(stage.parallel_group)
        return groups

    def get_stage_by_number(self, number: int) -> Stage | None:
        """Get a stage by its number."""
        for stage in self.stages:
            if stage.number == number:
                return stage
        return None

    def get_stage_branch(self, stage_number: int) -> str | None:
        """Get the branch name for a stage number."""
        stage = self.get_stage_by_number(stage_number)
        return stage.branch if stage else None

    def get_completed_stages(self) -> list[Stage]:
        """Get all stages with completed status."""
        return [s for s in self.stages if s.status == StageStatus.COMPLETED]

    def get_incomplete_stages(self) -> list[Stage]:
        """Get all stages that are not completed (pending or in_progress)."""
        return [s for s in self.stages if s.status != StageStatus.COMPLETED]


def _parse_stage_line(line: str, data: dict[str, object]) -> dict[str, object]:
    """Parse a single line from a stage section."""
    # Match: - **Field**: Value
    field_match = re.match(r"^-\s+\*\*([^*]+)\*\*:\s*(.*)$", line)
    if field_match:
        field_name = field_match.group(1).strip().lower().replace(" ", "_")
        value = field_match.group(2).strip()

        if field_name == "status":
            # Normalize status values
            status_map = {
                "pending": StageStatus.PENDING.value,
                "in_progress": StageStatus.IN_PROGRESS.value,
                "in progress": StageStatus.IN_PROGRESS.value,
                "completed": StageStatus.COMPLETED.value,
            }
            data["status"] = status_map.get(value.lower(), StageStatus.PENDING.value)
        elif field_name == "branch":
            data["branch"] = value
        elif field_name == "parallel_group":
            data["parallel_group"] = value
        elif field_name == "depends_on":
            data["depends_on"] = value if value.lower() != "none" else None
        elif field_name == "pr":
            # Extract PR number if present
            pr_match = re.search(r"#?(\d+)", value)
            data["pr_number"] = int(pr_match.group(1)) if pr_match else None
        elif field_name == "description":
            data["description"] = value

    # Match file list items: - [file.py]: description
    file_match = re.match(r"^\s+-\s+\[([^\]]+)\]:\s*(.*)$", line)
    if file_match:
        files_raw = data.get("files", [])
        files: list[str] = [str(f) for f in files_raw] if isinstance(files_raw, list) else []
        files.append(file_match.group(1))
        data["files"] = files

    # Match acceptance criteria: - [ ] or - [x] criterion
    criteria_match = re.match(r"^\s+-\s+\[[x ]\]\s+(.+)$", line, re.IGNORECASE)
    if criteria_match:
        criteria_raw = data.get("acceptance_criteria", [])
        if isinstance(criteria_raw, list):
            criteria: list[str] = [str(c) for c in criteria_raw]
        else:
            criteria = []
        criteria.append(criteria_match.group(1))
        data["acceptance_criteria"] = criteria

    return data
