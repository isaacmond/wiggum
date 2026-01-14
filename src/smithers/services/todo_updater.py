"""Service for updating TODO files in-place while preserving formatting."""

import re
from pathlib import Path

from smithers.logging_config import get_logger
from smithers.models.stage import StageStatus

logger = get_logger("smithers.services.todo_updater")


class TodoUpdater:
    """Updates TODO files in-place using regex replacement.

    This preserves the original formatting of the TODO file while updating
    specific fields like status and PR number.
    """

    def __init__(self, todo_file: Path) -> None:
        """Initialize the TodoUpdater.

        Args:
            todo_file: Path to the TODO file to update.
        """
        self.todo_file = todo_file

    def update_stage_status(
        self,
        stage_number: int,
        status: StageStatus,
        pr_number: int | None = None,
    ) -> bool:
        """Update a stage's status and optionally its PR number.

        Args:
            stage_number: The stage number to update.
            status: The new status for the stage.
            pr_number: Optional PR number to set.

        Returns:
            True if the update was successful, False otherwise.
        """
        if not self.todo_file.exists():
            logger.warning(f"TODO file not found: {self.todo_file}")
            return False

        content = self.todo_file.read_text()

        # Find the stage section using a pattern that captures until the next stage or section
        stage_pattern = rf"(### Stage {stage_number}:.*?)(?=### Stage \d+:|## Notes|$)"
        stage_match = re.search(stage_pattern, content, re.DOTALL)

        if not stage_match:
            logger.warning(f"Could not find Stage {stage_number} in TODO file")
            return False

        stage_section = stage_match.group(1)
        updated_section = stage_section

        # Update status field
        status_pattern = r"(\*\*Status\*\*:)\s*\S+"
        if re.search(status_pattern, updated_section):
            updated_section = re.sub(
                status_pattern,
                rf"\1 {status.value}",
                updated_section,
            )
        else:
            logger.warning(f"Could not find Status field in Stage {stage_number}")

        # Update PR number if provided
        if pr_number is not None:
            # Match PR field and everything after it until end of line (or end of string)
            pr_pattern = r"(\*\*PR\*\*:)[^\n]*"
            if re.search(pr_pattern, updated_section):
                updated_section = re.sub(
                    pr_pattern,
                    rf"\1 #{pr_number}",
                    updated_section,
                )
            else:
                logger.warning(f"Could not find PR field in Stage {stage_number}")

        # Replace the section in the original content
        updated_content = content.replace(stage_section, updated_section)
        self.todo_file.write_text(updated_content)

        logger.info(f"Updated Stage {stage_number}: status={status.value}, pr={pr_number}")
        return True

    def mark_stages_in_progress(self, stage_numbers: list[int]) -> None:
        """Mark multiple stages as in_progress.

        Args:
            stage_numbers: List of stage numbers to mark as in_progress.
        """
        for stage_num in stage_numbers:
            self.update_stage_status(stage_num, StageStatus.IN_PROGRESS)
