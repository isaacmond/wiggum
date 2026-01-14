"""Custom exceptions for Smithers."""


class SmithersError(Exception):
    """Base exception for all Smithers errors."""


class DependencyMissingError(SmithersError):
    """Raised when a required external dependency is not installed."""

    def __init__(self, dependencies: list[str]) -> None:
        self.dependencies = dependencies
        deps_str = ", ".join(dependencies)
        super().__init__(f"Missing required dependencies: {deps_str}")


class WorktreeError(SmithersError):
    """Raised when a git worktree operation fails."""


class TmuxError(SmithersError):
    """Raised when a tmux operation fails."""


class ClaudeError(SmithersError):
    """Raised when a Claude CLI operation fails."""


class GitHubError(SmithersError):
    """Raised when a GitHub CLI operation fails."""


class TodoParseError(SmithersError):
    """Raised when parsing a TODO file fails."""
