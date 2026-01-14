"""End-to-end tests for the CLI."""

from typer.testing import CliRunner

from wiggum import __version__
from wiggum.cli import app

runner = CliRunner()


class TestCLI:
    """Tests for the CLI interface."""

    def test_version(self) -> None:
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_help(self) -> None:
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "implement" in result.stdout
        assert "fix" in result.stdout

    def test_implement_help(self) -> None:
        """Test implement command help."""
        result = runner.invoke(app, ["implement", "--help"])
        assert result.exit_code == 0
        assert "design document" in result.stdout.lower()
        assert "--base" in result.stdout
        assert "--model" in result.stdout

    def test_fix_help(self) -> None:
        """Test fix command help."""
        result = runner.invoke(app, ["fix", "--help"])
        assert result.exit_code == 0
        assert "PR" in result.stdout
        assert "--model" in result.stdout

    def test_implement_missing_file(self) -> None:
        """Test implement with missing design doc."""
        result = runner.invoke(app, ["implement", "nonexistent.md"])
        assert result.exit_code != 0

    def test_fix_missing_pr_numbers(self) -> None:
        """Test fix with missing PR numbers."""
        result = runner.invoke(app, ["fix", "nonexistent.md"])
        assert result.exit_code != 0
