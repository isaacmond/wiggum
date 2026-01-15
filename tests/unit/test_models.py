"""Tests for data models."""

from smithers.models.config import Config, set_config
from smithers.models.stage import Stage, StageStatus
from smithers.services.claude import ClaudeResult


class TestConfig:
    """Tests for the Config model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = Config(branch_prefix="user/")

        assert config.branch_prefix == "user/"
        assert config.base_branch == "main"
        assert config.poll_interval == 5.0
        assert config.dry_run is False
        assert config.verbose is False

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = Config(
            branch_prefix="feature/",
            base_branch="develop",
            poll_interval=10.0,
            dry_run=True,
            verbose=True,
        )

        assert config.branch_prefix == "feature/"
        assert config.base_branch == "develop"
        assert config.poll_interval == 10.0
        assert config.dry_run is True
        assert config.verbose is True

    def test_set_config(self) -> None:
        """Test setting global config."""
        config = Config(branch_prefix="test/")
        set_config(config)
        # Just verify it doesn't raise an error
        assert config.branch_prefix == "test/"


class TestStage:
    """Tests for the Stage model."""

    def test_stage_from_dict(self) -> None:
        """Test creating a Stage from a dictionary."""
        data = {
            "number": 1,
            "title": "Test Stage",
            "branch": "feature/test",
            "parallel_group": "1",
            "description": "A test stage",
            "status": "pending",
            "depends_on": "Stage 0",
            "pr_number": 123,
            "files": ["file1.py", "file2.py"],
            "acceptance_criteria": ["Criterion 1", "Criterion 2"],
        }

        stage = Stage.from_dict(data)

        assert stage.number == 1
        assert stage.title == "Test Stage"
        assert stage.branch == "feature/test"
        assert stage.parallel_group == "1"
        assert stage.description == "A test stage"
        assert stage.status == StageStatus.PENDING
        assert stage.depends_on == "Stage 0"
        assert stage.pr_number == 123
        assert stage.files == ["file1.py", "file2.py"]
        assert stage.acceptance_criteria == ["Criterion 1", "Criterion 2"]

    def test_stage_status_enum(self) -> None:
        """Test StageStatus enum values."""
        assert StageStatus.PENDING.value == "pending"
        assert StageStatus.IN_PROGRESS.value == "in_progress"
        assert StageStatus.COMPLETED.value == "completed"


class TestClaudeResult:
    """Tests for the ClaudeResult model."""

    def test_extract_value(self) -> None:
        """Test extracting values from output."""
        result = ClaudeResult(
            output="TODO_FILE_CREATED: /path/to/file.md\nNUM_STAGES: 3",
            exit_code=0,
            success=True,
        )

        assert result.extract_value("TODO_FILE_CREATED") == "/path/to/file.md"
        assert result.extract_value("NONEXISTENT") is None

    def test_extract_int(self) -> None:
        """Test extracting integer values."""
        result = ClaudeResult(
            output="NUM_STAGES: 5\nPR_NUMBER: #123",
            exit_code=0,
            success=True,
        )

        assert result.extract_int("NUM_STAGES") == 5
        assert result.extract_int("PR_NUMBER") == 123
        assert result.extract_int("MISSING") is None
