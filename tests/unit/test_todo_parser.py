"""Tests for the TODO file parser."""

from pathlib import Path

import pytest

from smithers.exceptions import TodoParseError
from smithers.models.stage import StageStatus
from smithers.models.todo import TodoFile


class TestTodoFileParsing:
    """Tests for TodoFile.parse and TodoFile.parse_content."""

    def test_parse_file(self, sample_todo_file: Path) -> None:
        """Test parsing a TODO file from disk."""
        todo = TodoFile.parse(sample_todo_file)

        assert todo.path == sample_todo_file
        assert "Test Feature" in todo.title
        assert len(todo.stages) == 3

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that parsing a nonexistent file raises an error."""
        with pytest.raises(TodoParseError, match="not found"):
            TodoFile.parse(tmp_path / "nonexistent.md")

    def test_parse_content(self, sample_todo_content: str) -> None:
        """Test parsing TODO content directly."""
        todo = TodoFile.parse_content(sample_todo_content)

        assert "Test Feature" in todo.title
        assert "Testing the TODO parser" in todo.overview
        assert len(todo.stages) == 3

    def test_parse_stages(self, sample_todo_content: str) -> None:
        """Test that stages are parsed correctly."""
        todo = TodoFile.parse_content(sample_todo_content)

        # Stage 1
        stage1 = todo.stages[0]
        assert stage1.number == 1
        assert stage1.title == "Create Models"
        assert stage1.branch == "feature/models"
        assert stage1.parallel_group == "1"
        assert stage1.depends_on is None
        assert stage1.status == StageStatus.PENDING
        assert "models/user.py" in stage1.files
        assert "models/settings.py" in stage1.files
        assert len(stage1.acceptance_criteria) == 2

        # Stage 2
        stage2 = todo.stages[1]
        assert stage2.number == 2
        assert stage2.title == "Create API"
        assert stage2.branch == "feature/api"
        assert stage2.parallel_group == "1"

        # Stage 3
        stage3 = todo.stages[2]
        assert stage3.number == 3
        assert stage3.title == "Integration"
        assert stage3.parallel_group == "2"
        assert stage3.depends_on is not None
        assert "Stage 1" in stage3.depends_on

    def test_parse_notes(self, sample_todo_content: str) -> None:
        """Test that notes section is parsed."""
        todo = TodoFile.parse_content(sample_todo_content)
        assert "test implementation plan" in todo.notes


class TestTodoFileQueries:
    """Tests for TodoFile query methods."""

    def test_get_stages_by_group(self, sample_todo_content: str) -> None:
        """Test grouping stages by parallel group."""
        todo = TodoFile.parse_content(sample_todo_content)
        groups = todo.get_stages_by_group()

        assert "1" in groups
        assert "2" in groups
        assert len(groups["1"]) == 2  # Stages 1 and 2
        assert len(groups["2"]) == 1  # Stage 3

    def test_get_parallel_groups_in_order(self, sample_todo_content: str) -> None:
        """Test getting parallel groups in order."""
        todo = TodoFile.parse_content(sample_todo_content)
        groups = todo.get_parallel_groups_in_order()

        assert groups == ["1", "2"]

    def test_get_stage_by_number(self, sample_todo_content: str) -> None:
        """Test getting a stage by its number."""
        todo = TodoFile.parse_content(sample_todo_content)

        stage = todo.get_stage_by_number(2)
        assert stage is not None
        assert stage.number == 2
        assert stage.title == "Create API"

        # Non-existent stage
        assert todo.get_stage_by_number(99) is None

    def test_get_stage_branch(self, sample_todo_content: str) -> None:
        """Test getting a branch name by stage number."""
        todo = TodoFile.parse_content(sample_todo_content)

        assert todo.get_stage_branch(1) == "feature/models"
        assert todo.get_stage_branch(2) == "feature/api"
        assert todo.get_stage_branch(99) is None


class TestEdgeCases:
    """Tests for edge cases in parsing."""

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        todo = TodoFile.parse_content("")
        assert todo.title == ""
        assert len(todo.stages) == 0

    def test_minimal_stage(self) -> None:
        """Test parsing a minimal stage definition."""
        content = """# Plan

## Stages

### Stage 1: Minimal
- **Branch**: minimal-branch
- **Parallel group**: 1
"""
        todo = TodoFile.parse_content(content)
        assert len(todo.stages) == 1
        assert todo.stages[0].branch == "minimal-branch"

    def test_completed_status(self) -> None:
        """Test parsing completed status."""
        content = """# Plan

## Stages

### Stage 1: Done
- **Status**: completed
- **Branch**: done-branch
- **Parallel group**: 1
- **PR**: #123
"""
        todo = TodoFile.parse_content(content)
        assert todo.stages[0].status == StageStatus.COMPLETED
        assert todo.stages[0].pr_number == 123


class TestTodoFileFiltering:
    """Tests for TodoFile filtering methods."""

    def test_get_completed_stages_none(self, sample_todo_content: str) -> None:
        """Test get_completed_stages when no stages are completed."""
        todo = TodoFile.parse_content(sample_todo_content)

        completed = todo.get_completed_stages()

        assert len(completed) == 0

    def test_get_completed_stages_some(self) -> None:
        """Test get_completed_stages with mixed statuses."""
        content = """# Plan

## Stages

### Stage 1: Done
- **Status**: completed
- **Branch**: branch-1
- **Parallel group**: 1
- **PR**: #100

### Stage 2: In Progress
- **Status**: in_progress
- **Branch**: branch-2
- **Parallel group**: 1

### Stage 3: Pending
- **Status**: pending
- **Branch**: branch-3
- **Parallel group**: 2
"""
        todo = TodoFile.parse_content(content)

        completed = todo.get_completed_stages()

        assert len(completed) == 1
        assert completed[0].number == 1
        assert completed[0].status == StageStatus.COMPLETED

    def test_get_incomplete_stages_all(self, sample_todo_content: str) -> None:
        """Test get_incomplete_stages when all are pending."""
        todo = TodoFile.parse_content(sample_todo_content)

        incomplete = todo.get_incomplete_stages()

        assert len(incomplete) == 3
        for stage in incomplete:
            assert stage.status != StageStatus.COMPLETED

    def test_get_incomplete_stages_mixed(self) -> None:
        """Test get_incomplete_stages with mixed statuses."""
        content = """# Plan

## Stages

### Stage 1: Done
- **Status**: completed
- **Branch**: branch-1
- **Parallel group**: 1
- **PR**: #100

### Stage 2: In Progress
- **Status**: in_progress
- **Branch**: branch-2
- **Parallel group**: 1

### Stage 3: Pending
- **Status**: pending
- **Branch**: branch-3
- **Parallel group**: 2
"""
        todo = TodoFile.parse_content(content)

        incomplete = todo.get_incomplete_stages()

        assert len(incomplete) == 2
        assert incomplete[0].number == 2
        assert incomplete[0].status == StageStatus.IN_PROGRESS
        assert incomplete[1].number == 3
        assert incomplete[1].status == StageStatus.PENDING

    def test_get_completed_stages_all(self) -> None:
        """Test get_completed_stages when all are completed."""
        content = """# Plan

## Stages

### Stage 1: Done
- **Status**: completed
- **Branch**: branch-1
- **Parallel group**: 1
- **PR**: #100

### Stage 2: Also Done
- **Status**: completed
- **Branch**: branch-2
- **Parallel group**: 1
- **PR**: #101
"""
        todo = TodoFile.parse_content(content)

        completed = todo.get_completed_stages()
        incomplete = todo.get_incomplete_stages()

        assert len(completed) == 2
        assert len(incomplete) == 0
