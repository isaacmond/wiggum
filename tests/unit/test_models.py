"""Tests for data models."""

from smithers.models.config import Config, get_config, set_config
from smithers.models.stage import Stage, StageStatus
from smithers.services.claude import ClaudeResult


class TestConfig:
    """Tests for the Config model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = Config()

        assert config.model == "claude-opus-4-5-20251101"
        assert config.base_branch == "main"
        assert config.poll_interval == 5.0
        assert config.dry_run is False
        assert config.verbose is False

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = Config(
            model="claude-sonnet",
            base_branch="develop",
            poll_interval=10.0,
            dry_run=True,
            verbose=True,
        )

        assert config.model == "claude-sonnet"
        assert config.base_branch == "develop"
        assert config.poll_interval == 10.0
        assert config.dry_run is True
        assert config.verbose is True

    def test_global_config(self) -> None:
        """Test getting and setting global config."""
        config = Config(model="test-model")
        set_config(config)

        retrieved = get_config()
        assert retrieved.model == "test-model"


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

    def test_stage_to_dict(self) -> None:
        """Test converting a Stage to a dictionary."""
        stage = Stage(
            number=1,
            title="Test",
            branch="test",
            parallel_group="1",
            description="Test desc",
            status=StageStatus.COMPLETED,
            depends_on="Stage 0",
            pr_number=456,
            files=["file.py"],
            acceptance_criteria=["Done"],
        )

        data = stage.to_dict()

        assert data["number"] == 1
        assert data["status"] == "completed"
        assert data["pr_number"] == 456

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

    def test_has_flag(self) -> None:
        """Test checking boolean flags."""
        result = ClaudeResult(
            output="ALL_DONE: true\nCI_PASSING: false",
            exit_code=0,
            success=True,
        )

        assert result.has_flag("ALL_DONE") is True
        assert result.has_flag("CI_PASSING") is False
        assert result.has_flag("MISSING") is False
