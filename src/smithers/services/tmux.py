"""Tmux session management service."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from smithers.console import console, create_progress, print_info
from smithers.exceptions import DependencyMissingError, TmuxError


@dataclass
class TmuxService:
    """Service for managing tmux sessions."""

    def check_dependencies(self) -> list[str]:
        """Check for required dependencies and return list of missing ones."""
        missing: list[str] = []

        try:
            subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("tmux")

        return missing

    def ensure_dependencies(self) -> None:
        """Ensure all required dependencies are installed."""
        missing = self.check_dependencies()
        if missing:
            raise DependencyMissingError(missing)

    @staticmethod
    def sanitize_session_name(branch: str) -> str:
        """Convert a branch name to a valid tmux session name.

        Replaces slashes with dashes since tmux doesn't allow slashes in session names.

        Args:
            branch: The branch name

        Returns:
            A sanitized session name
        """
        return branch.replace("/", "-")

    def create_session(
        self,
        name: str,
        workdir: Path,
        command: str,
    ) -> str:
        """Create a new tmux session running the given command.

        Args:
            name: Session name (will be sanitized)
            workdir: Working directory for the session
            command: Command to run in the session

        Returns:
            The sanitized session name

        Raises:
            TmuxError: If session creation fails
        """
        session = self.sanitize_session_name(name)
        print_info(f"Starting tmux session '{session}' at {workdir}")

        try:
            subprocess.run(
                [
                    "tmux",
                    "new-session",
                    "-d",  # Detached
                    "-s",
                    session,
                    "-c",
                    str(workdir),
                    command,
                ],
                capture_output=True,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise TmuxError(f"Failed to create tmux session '{session}': {e.stderr}") from e

        return session

    def session_exists(self, name: str) -> bool:
        """Check if a tmux session exists.

        Args:
            name: Session name (will be sanitized)

        Returns:
            True if the session exists
        """
        session = self.sanitize_session_name(name)
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def wait_for_sessions(
        self,
        sessions: list[str],
        poll_interval: float = 5.0,
    ) -> None:
        """Wait for multiple tmux sessions to complete.

        Args:
            sessions: List of session names to wait for
            poll_interval: Seconds between status checks
        """
        remaining = list(sessions)

        console.print(f"Waiting for {len(sessions)} session(s) to complete...")

        with create_progress() as progress:
            task = progress.add_task(
                f"[cyan]Waiting for {len(remaining)} sessions...",
                total=None,
            )

            while remaining:
                still_running: list[str] = []
                for session in remaining:
                    if self.session_exists(session):
                        still_running.append(session)
                    else:
                        console.print(f"  [green]Session '{session}' completed[/green]")

                remaining = still_running

                if remaining:
                    shown = ", ".join(remaining[:3])
                    suffix = "..." if len(remaining) > 3 else ""
                    progress.update(
                        task,
                        description=f"[cyan]Waiting for {len(remaining)} sessions: {shown}{suffix}",
                    )
                    time.sleep(poll_interval)

        console.print("[green]All sessions completed[/green]")

    def kill_session(self, name: str) -> None:
        """Kill a tmux session if it exists.

        Args:
            name: Session name (will be sanitized)
        """
        session = self.sanitize_session_name(name)
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
            check=False,
        )

    def kill_all_smithers_sessions(self) -> None:
        """Kill all tmux sessions that appear to be smithers-related."""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                check=True,
                text=True,
            )
            sessions = result.stdout.strip().split("\n")

            for session_name in sessions:
                name = session_name.strip()
                if not name:
                    continue
                # Kill sessions that look like branch names (start with letter, not just numbers)
                if name[0].isalpha() and not name.isdigit():
                    self.kill_session(name)
        except subprocess.CalledProcessError:
            pass  # No sessions or tmux not running
