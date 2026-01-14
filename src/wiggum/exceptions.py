"""Custom exceptions for Wiggum."""


class WiggumError(Exception):
    """Base exception for all Wiggum errors."""


class DependencyMissingError(WiggumError):
    """Raised when a required external dependency is not installed."""

    def __init__(self, dependencies: list[str]) -> None:
        self.dependencies = dependencies
        deps_str = ", ".join(dependencies)
        super().__init__(f"Missing required dependencies: {deps_str}")


class WorktreeError(WiggumError):
    """Raised when a git worktree operation fails."""


class TmuxError(WiggumError):
    """Raised when a tmux operation fails."""


class ClaudeError(WiggumError):
    """Raised when a Claude CLI operation fails."""


class GitHubError(WiggumError):
    """Raised when a GitHub CLI operation fails."""


class TodoParseError(WiggumError):
    """Raised when parsing a TODO file fails."""
