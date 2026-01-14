"""Logging configuration for Smithers CLI."""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from smithers.models.config import Config

# Module-level state for session tracking
_session_id: str | None = None
_log_dir: Path | None = None
_session_log_file: Path | None = None
_initialized: bool = False

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_log_dir() -> Path:
    """Get the logging directory, creating it if necessary."""
    global _log_dir  # noqa: PLW0603
    if _log_dir is None:
        _log_dir = Path.home() / ".smithers" / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def get_session_id() -> str:
    """Get the current session ID, creating one if necessary."""
    global _session_id  # noqa: PLW0603
    if _session_id is None:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        _session_id = f"{timestamp}-{short_uuid}"
    return _session_id


def get_session_log_file() -> Path:
    """Get the session-specific log file path."""
    global _session_log_file  # noqa: PLW0603
    if _session_log_file is None:
        log_dir = get_log_dir()
        session_id = get_session_id()
        _session_log_file = log_dir / f"smithers-{session_id}.log"
    return _session_log_file


def setup_logging(config: Config | None = None) -> None:
    """Initialize the logging system.

    Args:
        config: Optional config to determine verbosity. If verbose=True,
                logs DEBUG to file; otherwise INFO.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return

    log_level = logging.DEBUG if (config and config.verbose) else logging.INFO

    # Get the root smithers logger
    root_logger = logging.getLogger("smithers")
    root_logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # 1. Session-specific file handler (captures everything for this run)
    session_file = get_session_log_file()
    session_handler = logging.FileHandler(session_file, encoding="utf-8")
    session_handler.setLevel(log_level)
    session_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(session_handler)

    # 2. Rotating file handler for combined log (historical analysis)
    combined_log = get_log_dir() / "smithers.log"
    rotating_handler = RotatingFileHandler(
        combined_log,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,  # Keep 5 rotated files
        encoding="utf-8",
    )
    rotating_handler.setLevel(logging.INFO)  # Combined log always at INFO
    rotating_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(rotating_handler)

    _initialized = True

    # Log session start
    root_logger.info("=" * 60)
    root_logger.info(f"Smithers session started: {get_session_id()}")
    root_logger.info(f"Session log file: {session_file}")
    root_logger.info(f"Python: {sys.version.split()[0]}")
    root_logger.info(f"Working directory: {Path.cwd()}")
    root_logger.info("=" * 60)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Module name (e.g., "smithers.services.tmux")

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_subprocess_result(
    logger: logging.Logger,
    cmd: list[str] | str,
    exit_code: int,
    stdout: str | None = None,
    stderr: str | None = None,
    success: bool = True,
) -> None:
    """Log the result of a subprocess call.

    Args:
        logger: The logger to use
        cmd: Command that was executed
        exit_code: Process exit code
        stdout: Captured stdout (if any)
        stderr: Captured stderr (if any)
        success: Whether the operation succeeded
    """
    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    level = logging.DEBUG if success else logging.WARNING

    logger.log(level, f"Subprocess: {cmd_str}")
    logger.log(level, f"  Exit code: {exit_code}")

    if stdout and stdout.strip():
        for line in stdout.strip().split("\n")[:50]:  # Limit to 50 lines
            logger.log(level, f"  stdout: {line}")
        if stdout.strip().count("\n") > 50:
            logger.log(level, "  stdout: ... (truncated)")

    if stderr and stderr.strip():
        for line in stderr.strip().split("\n")[:50]:  # Limit to 50 lines
            logger.log(level, f"  stderr: {line}")
        if stderr.strip().count("\n") > 50:
            logger.log(level, "  stderr: ... (truncated)")


def cleanup_old_logs(max_age_days: int = 30) -> None:
    """Remove session log files older than max_age_days.

    Args:
        max_age_days: Delete logs older than this many days
    """
    log_dir = get_log_dir()
    cutoff = datetime.now(tz=UTC).timestamp() - (max_age_days * 24 * 60 * 60)

    logger = get_logger("smithers.logging")

    for log_file in log_dir.glob("smithers-*.log"):
        # Don't delete the combined log or current session log
        if log_file.name == "smithers.log":
            continue
        if _session_log_file and log_file == _session_log_file:
            continue

        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                logger.debug(f"Cleaned up old log file: {log_file}")
        except OSError as e:
            logger.warning(f"Failed to clean up log file {log_file}: {e}")


def cleanup_old_sessions(max_age_days: int = 7) -> None:
    """Remove old session output directories.

    Args:
        max_age_days: Delete session directories older than this many days
    """
    import shutil

    sessions_dir = Path.home() / ".smithers" / "sessions"
    if not sessions_dir.exists():
        return

    cutoff = datetime.now(tz=UTC).timestamp() - (max_age_days * 24 * 60 * 60)
    logger = get_logger("smithers.logging")

    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue

        try:
            # Use the directory's modification time
            if session_dir.stat().st_mtime < cutoff:
                shutil.rmtree(session_dir)
                logger.debug(f"Cleaned up old session directory: {session_dir}")
        except OSError as e:
            logger.warning(f"Failed to clean up session directory {session_dir}: {e}")
