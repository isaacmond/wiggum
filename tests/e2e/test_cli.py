"""End-to-end tests for the CLI."""

import importlib
import re

import pytest
from typer.testing import CliRunner

from smithers import __version__
from smithers.cli import app

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


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
        assert "update" in result.stdout

    def test_implement_help(self) -> None:
        """Test implement command help."""
        result = runner.invoke(app, ["implement", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.stdout)
        assert "design document" in output.lower()
        assert "--base" in output
        assert "--model" in output

    def test_fix_help(self) -> None:
        """Test fix command help."""
        result = runner.invoke(app, ["fix", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.stdout)
        assert "PR" in output
        assert "--model" in output

    def test_update_help(self) -> None:
        """Test update command help."""
        result = runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.stdout)
        assert "update" in output.lower()
        assert "uv tool upgrade smithers" in output

    def test_update_command_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test update command execution without calling uv."""

        def fake_which(cmd: str) -> str | None:
            return "/usr/bin/uv" if cmd == "uv" else None

        class FakeResult:
            stdout = "Already up to date"
            stderr = ""

        def fake_run(
            command: list[str],
            capture_output: bool,
            text: bool,
            check: bool,
        ) -> FakeResult:  # type: ignore[override]
            assert command == ["uv", "tool", "upgrade", "smithers"]
            assert capture_output is True
            assert text is True
            assert check is True
            return FakeResult()

        update_module = importlib.import_module("smithers.commands.update")
        monkeypatch.setattr(update_module, "which", fake_which)
        monkeypatch.setattr(update_module.subprocess, "run", fake_run)

        result = runner.invoke(app, ["update"])
        assert result.exit_code == 0
        assert "up to date" in result.stdout.lower()

    def test_update_self_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test update-self alias uses the same logic."""

        def fake_which(cmd: str) -> str | None:
            return "/usr/bin/uv" if cmd == "uv" else None

        class FakeResult:
            stdout = "Updated"
            stderr = ""

        def fake_run(
            command: list[str],
            capture_output: bool,
            text: bool,
            check: bool,
        ) -> FakeResult:  # type: ignore[override]
            assert command == ["uv", "tool", "upgrade", "smithers"]
            return FakeResult()

        update_module = importlib.import_module("smithers.commands.update")
        monkeypatch.setattr(update_module, "which", fake_which)
        monkeypatch.setattr(update_module.subprocess, "run", fake_run)

        result = runner.invoke(app, ["update-self"])
        assert result.exit_code == 0
        assert "updated" in result.stdout.lower()

    def test_implement_missing_file(self) -> None:
        """Test implement with missing design doc."""
        result = runner.invoke(app, ["implement", "nonexistent.md"])
        assert result.exit_code != 0

    def test_fix_missing_pr_numbers(self) -> None:
        """Test fix with missing PR numbers."""
        result = runner.invoke(app, ["fix", "nonexistent.md"])
        assert result.exit_code != 0
