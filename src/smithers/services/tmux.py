"""Tmux session management service."""

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from smithers.console import console, create_progress, print_info
from smithers.exceptions import DependencyMissingError, TmuxError


@dataclass
class SessionInfo:
    """Information about a saved smithers session."""

    session_name: str
    reconnect_command: str
    started: str = ""
    command: str = ""


@dataclass
class RunningSession:
    """Information about a running tmux session."""

    name: str
    windows: int = 1
    attached: bool = False
    created: str = ""


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

        Replaces slashes and spaces with dashes since tmux doesn't allow them
        in session names.

        Args:
            branch: The branch name

        Returns:
            A sanitized session name
        """
        return branch.replace("/", "-").replace(" ", "-")

    def ensure_rejoinable_session(self, session_name: str, argv: list[str]) -> None:
        """Run smithers inside tmux so it can be reattached if the terminal drops.

        This method is a no-op when already inside tmux, when wrapping is
        explicitly disabled, or when running in a non-TTY environment (e.g.
        tests or redirected output).
        """
        if os.environ.get("SMITHERS_TMUX_WRAPPED") == "1":
            return
        if os.environ.get("SMITHERS_DISABLE_TMUX_WRAPPER") == "1":
            return
        if os.environ.get("TMUX"):
            return
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return

        self.ensure_dependencies()

        session = self.sanitize_session_name(session_name)
        command = " ".join(shlex.quote(arg) for arg in argv)
        tmux_cmd = [
            "tmux",
            "new-session",
            "-A",
            "-s",
            session,
            f"SMITHERS_TMUX_WRAPPED=1 {command}",
        ]

        print_info(
            f"Running smithers in tmux session '{session}' so you can reattach if disconnected."
        )
        console.print(f"Reconnect anytime with: [cyan]tmux attach -t {session}[/cyan]")
        self._record_last_session_hint(session=session, command=command)

        try:
            result = subprocess.run(
                tmux_cmd,
                check=False,
                text=True,
            )
        except subprocess.SubprocessError as e:
            raise TmuxError(f"Failed to start tmux session '{session}': {e}") from e

        raise SystemExit(result.returncode)

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

    def _record_last_session_hint(self, session: str, command: str) -> None:
        """Persist the last session name so users can reattach after a crash."""
        try:
            state_dir = Path.home() / ".smithers"
            state_dir.mkdir(parents=True, exist_ok=True)
            hint_file = state_dir / "last_session.txt"
            hint_file.write_text(
                "\n".join(
                    [
                        f"session={session}",
                        f"reconnect=tmux attach -t {session}",
                        f"started={time.strftime('%Y-%m-%d %H:%M:%S')}",
                        f"command={command}",
                    ]
                )
                + "\n"
            )
        except OSError:
            # If we cannot persist the hint, we can still continue safely.
            pass

    def get_last_session(self) -> SessionInfo | None:
        """Read the last session hint file.

        Returns:
            SessionInfo if the hint file exists and is valid, None otherwise.
        """
        hint_file = Path.home() / ".smithers" / "last_session.txt"
        if not hint_file.exists():
            return None

        try:
            content = hint_file.read_text()
            data: dict[str, str] = {}
            for line in content.strip().split("\n"):
                if "=" in line:
                    key, _, value = line.partition("=")
                    data[key.strip()] = value.strip()

            session_name = data.get("session")
            reconnect = data.get("reconnect")
            if not session_name or not reconnect:
                return None

            return SessionInfo(
                session_name=session_name,
                reconnect_command=reconnect,
                started=data.get("started", ""),
                command=data.get("command", ""),
            )
        except OSError:
            return None

    def list_smithers_sessions(self) -> list[RunningSession]:
        """List all running tmux sessions that appear to be smithers-related.

        Returns:
            List of RunningSession objects for smithers sessions.
        """
        try:
            # Format: session_name:num_windows:attached:created_timestamp
            result = subprocess.run(
                [
                    "tmux",
                    "list-sessions",
                    "-F",
                    "#{session_name}:#{session_windows}:#{session_attached}:#{session_created}",
                ],
                capture_output=True,
                check=True,
                text=True,
            )

            sessions: list[RunningSession] = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    name = parts[0]
                    # Only include smithers-related sessions (start with "smithers-")
                    if name.startswith("smithers-"):
                        sessions.append(
                            RunningSession(
                                name=name,
                                windows=int(parts[1]) if parts[1].isdigit() else 1,
                                attached=parts[2] == "1",
                                created=parts[3] if len(parts) > 3 else "",
                            )
                        )
            return sessions
        except subprocess.CalledProcessError:
            return []  # No sessions or tmux not running
        except FileNotFoundError:
            return []  # tmux not installed

    def attach_session(self, session_name: str) -> int:
        """Attach to an existing tmux session.

        Args:
            session_name: Name of the session to attach to.

        Returns:
            The exit code from tmux attach.

        Raises:
            TmuxError: If the session doesn't exist.
        """
        if not self.session_exists(session_name):
            raise TmuxError(f"Session '{session_name}' does not exist.")

        # Use exec to replace the current process with tmux attach
        result = subprocess.run(
            ["tmux", "attach", "-t", session_name],
            check=False,
        )
        return result.returncode
