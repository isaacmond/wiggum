"""Tests for the TodoUpdater service."""

from pathlib import Path

import pytest

from smithers.models.stage import StageStatus
from smithers.services.todo_updater import TodoUpdater


@pytest.fixture
def todo_with_pending_stages() -> str:
    """Return TODO content with pending stages."""
    return """# Implementation Plan: Test Feature

## Overview
Testing checkpoint functionality.

## Stages

### Stage 1: Create Models
- **Status**: pending
- **Branch**: feature/models
- **Parallel group**: 1
- **Depends on**: none
- **PR**: (to be filled in)
- **Description**: Create the data models

### Stage 2: Create API
- **Status**: pending
- **Branch**: feature/api
- **Parallel group**: 1
- **Depends on**: none
- **PR**: (to be filled in)
- **Description**: Create API endpoints

### Stage 3: Integration
- **Status**: pending
- **Branch**: feature/integration
- **Parallel group**: 2
- **Depends on**: feature/models
- **PR**: (to be filled in)
- **Description**: Integrate everything

## Notes
Test notes.
"""


@pytest.fixture
def todo_file_path(tmp_path: Path, todo_with_pending_stages: str) -> Path:
    """Create a TODO file and return its path."""
    todo_file = tmp_path / "test-todo.md"
    todo_file.write_text(todo_with_pending_stages)
    return todo_file


class TestTodoUpdaterStatusUpdate:
    """Tests for updating stage status."""

    def test_update_status_pending_to_in_progress(self, todo_file_path: Path) -> None:
        """Test updating a pending stage to in_progress."""
        updater = TodoUpdater(todo_file_path)

        result = updater.update_stage_status(1, StageStatus.IN_PROGRESS)

        assert result is True
        content = todo_file_path.read_text()
        assert "**Status**: in_progress" in content
        # Other stages should still be pending
        assert content.count("**Status**: pending") == 2

    def test_update_status_to_completed_with_pr(self, todo_file_path: Path) -> None:
        """Test updating status to completed with PR number."""
        updater = TodoUpdater(todo_file_path)

        result = updater.update_stage_status(
            stage_number=1,
            status=StageStatus.COMPLETED,
            pr_number=42,
        )

        assert result is True
        content = todo_file_path.read_text()
        assert "**Status**: completed" in content
        assert "**PR**: #42" in content

    def test_update_preserves_other_content(self, todo_file_path: Path) -> None:
        """Test that updating preserves other content in the file."""
        updater = TodoUpdater(todo_file_path)

        updater.update_stage_status(1, StageStatus.COMPLETED, pr_number=99)

        content = todo_file_path.read_text()
        # Check that other sections are preserved
        assert "# Implementation Plan: Test Feature" in content
        assert "## Overview" in content
        assert "Testing checkpoint functionality." in content
        assert "## Notes" in content
        assert "Test notes." in content
        # Check other stages are preserved
        assert "### Stage 2: Create API" in content
        assert "### Stage 3: Integration" in content

    def test_update_nonexistent_stage(self, todo_file_path: Path) -> None:
        """Test that updating a nonexistent stage returns False."""
        updater = TodoUpdater(todo_file_path)

        result = updater.update_stage_status(99, StageStatus.COMPLETED)

        assert result is False
        # Original content should be unchanged
        content = todo_file_path.read_text()
        assert content.count("**Status**: pending") == 3

    def test_update_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that updating a nonexistent file returns False."""
        updater = TodoUpdater(tmp_path / "nonexistent.md")

        result = updater.update_stage_status(1, StageStatus.COMPLETED)

        assert result is False


class TestTodoUpdaterMarkInProgress:
    """Tests for marking multiple stages as in_progress."""

    def test_mark_single_stage_in_progress(self, todo_file_path: Path) -> None:
        """Test marking a single stage as in_progress."""
        updater = TodoUpdater(todo_file_path)

        updater.mark_stages_in_progress([1])

        content = todo_file_path.read_text()
        assert content.count("**Status**: in_progress") == 1
        assert content.count("**Status**: pending") == 2

    def test_mark_multiple_stages_in_progress(self, todo_file_path: Path) -> None:
        """Test marking multiple stages as in_progress."""
        updater = TodoUpdater(todo_file_path)

        updater.mark_stages_in_progress([1, 2])

        content = todo_file_path.read_text()
        assert content.count("**Status**: in_progress") == 2
        assert content.count("**Status**: pending") == 1

    def test_mark_all_stages_in_progress(self, todo_file_path: Path) -> None:
        """Test marking all stages as in_progress."""
        updater = TodoUpdater(todo_file_path)

        updater.mark_stages_in_progress([1, 2, 3])

        content = todo_file_path.read_text()
        assert content.count("**Status**: in_progress") == 3
        assert content.count("**Status**: pending") == 0


class TestTodoUpdaterEdgeCases:
    """Tests for edge cases in TodoUpdater."""

    def test_update_stage_at_end_of_file(self, tmp_path: Path) -> None:
        """Test updating a stage at the end of the file (no following sections)."""
        content = """# Plan

## Stages

### Stage 1: Only Stage
- **Status**: pending
- **Branch**: only-branch
- **Parallel group**: 1
- **PR**: (to be filled in)
"""
        todo_file = tmp_path / "todo.md"
        todo_file.write_text(content)

        updater = TodoUpdater(todo_file)
        result = updater.update_stage_status(1, StageStatus.COMPLETED, pr_number=123)

        assert result is True
        updated = todo_file.read_text()
        assert "**Status**: completed" in updated
        assert "**PR**: #123" in updated

    def test_update_middle_stage(self, todo_file_path: Path) -> None:
        """Test updating a stage in the middle of multiple stages."""
        updater = TodoUpdater(todo_file_path)

        result = updater.update_stage_status(2, StageStatus.COMPLETED, pr_number=456)

        assert result is True
        content = todo_file_path.read_text()

        # Check stage 2 is updated
        # Find stage 2 section and verify it has completed status
        stage2_start = content.find("### Stage 2:")
        stage3_start = content.find("### Stage 3:")
        stage2_section = content[stage2_start:stage3_start]

        assert "**Status**: completed" in stage2_section
        assert "**PR**: #456" in stage2_section

        # Check stages 1 and 3 are still pending
        stage1_start = content.find("### Stage 1:")
        stage1_section = content[stage1_start:stage2_start]
        assert "**Status**: pending" in stage1_section

        stage3_section = content[stage3_start:]
        assert "**Status**: pending" in stage3_section

    def test_pr_number_formats_are_normalized(self, tmp_path: Path) -> None:
        """Test that various PR formats are handled correctly."""
        content = """# Plan

## Stages

### Stage 1: Test
- **Status**: pending
- **Branch**: test-branch
- **Parallel group**: 1
- **PR**: #existing-number
"""
        todo_file = tmp_path / "todo.md"
        todo_file.write_text(content)

        updater = TodoUpdater(todo_file)
        updater.update_stage_status(1, StageStatus.COMPLETED, pr_number=789)

        updated = todo_file.read_text()
        assert "**PR**: #789" in updated

    def test_sequential_updates_work(self, todo_file_path: Path) -> None:
        """Test that multiple sequential updates work correctly."""
        updater = TodoUpdater(todo_file_path)

        # Mark as in_progress first
        updater.update_stage_status(1, StageStatus.IN_PROGRESS)
        content = todo_file_path.read_text()
        assert "**Status**: in_progress" in content

        # Then mark as completed with PR
        updater.update_stage_status(1, StageStatus.COMPLETED, pr_number=100)
        content = todo_file_path.read_text()

        # Find stage 1 section
        stage1_start = content.find("### Stage 1:")
        stage2_start = content.find("### Stage 2:")
        stage1_section = content[stage1_start:stage2_start]

        assert "**Status**: completed" in stage1_section
        assert "**PR**: #100" in stage1_section
