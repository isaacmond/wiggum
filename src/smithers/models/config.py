"""Runtime configuration for Smithers."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration for Smithers operations."""

    # Claude settings
    model: str = "claude-opus-4-5-20251101"
    dangerously_skip_permissions: bool = True

    # Git settings
    base_branch: str = "main"
    branch_prefix: str = ""  # e.g., "username/" for branches like "username/stage-1-models"

    # Tmux settings
    poll_interval: float = 5.0  # seconds between session status checks

    # Output settings
    verbose: bool = False
    dry_run: bool = False

    # Paths
    temp_dir: Path = field(default_factory=lambda: Path("/tmp"))
    plans_dir: Path = field(default_factory=lambda: Path.home() / ".smithers" / "plans")
    sessions_dir: Path = field(default_factory=lambda: Path.home() / ".smithers" / "sessions")

    def __post_init__(self) -> None:
        """Ensure required directories exist."""
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    # Tracked state (mutable during execution)
    created_worktrees: list[str] = field(default_factory=list)


# Global config instance (can be overridden via CLI)
_config: Config | None = None


def get_config() -> Config:
    """Get the current configuration, creating a default if none exists."""
    global _config  # noqa: PLW0603
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration."""
    global _config  # noqa: PLW0603
    _config = config
