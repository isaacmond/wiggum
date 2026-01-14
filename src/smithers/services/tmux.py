"""Tmux session management service."""

import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from smithers.console import (
    console,
    create_progress,
    print_detach_message,
    print_info,
    print_session_complete,
)
from smithers.exceptions import DependencyMissingError, TmuxError
from smithers.logging_config import get_logger, log_subprocess_result

logger = get_logger("smithers.services.tmux")

# Default sessions directory
DEFAULT_SESSIONS_DIR = Path.home() / ".smithers" / "sessions"


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
        logger.debug("Checking tmux dependencies")
        missing: list[str] = []

        try:
            result = subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.debug(f"tmux version: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("tmux not found or not working")
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

        Creates a detached tmux session and streams output to the console in real-time.
        User can press Ctrl+C to detach without killing the session.

        This method is a no-op when already inside tmux, when wrapping is
        explicitly disabled, or when running in a non-TTY environment (e.g.
        tests or redirected output).
        """
        logger.debug(f"ensure_rejoinable_session called: session_name={session_name}")
        logger.debug(f"  argv={argv}")
        logger.debug(f"  SMITHERS_TMUX_WRAPPED={os.environ.get('SMITHERS_TMUX_WRAPPED')}")
        disable_wrapper = os.environ.get("SMITHERS_DISABLE_TMUX_WRAPPER")
        logger.debug(f"  SMITHERS_DISABLE_TMUX_WRAPPER={disable_wrapper}")
        logger.debug(f"  TMUX={os.environ.get('TMUX')}")
        logger.debug(f"  stdin.isatty={sys.stdin.isatty()}, stdout.isatty={sys.stdout.isatty()}")

        if os.environ.get("SMITHERS_TMUX_WRAPPED") == "1":
            logger.info("Already inside tmux wrapper, continuing execution")
            return
        if os.environ.get("SMITHERS_DISABLE_TMUX_WRAPPER") == "1":
            logger.info("Tmux wrapper disabled via SMITHERS_DISABLE_TMUX_WRAPPER")
            return
        if os.environ.get("TMUX"):
            logger.info("Already inside tmux, skipping wrapper")
            return
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            logger.info("Non-TTY environment, skipping tmux wrapper")
            return

        self.ensure_dependencies()

        session = self.sanitize_session_name(session_name)
        session_dir = self._get_session_dir(session)
        output_log = session_dir / "output.log"
        exit_code_file = session_dir / "exit_code"

        # Build the inner command with script wrapper
        inner_command = " ".join(shlex.quote(arg) for arg in argv)
        # Use script to capture terminal output to a file
        # The command writes exit code to a file before exiting
        wrapped_command = (
            f"SMITHERS_TMUX_WRAPPED=1 {inner_command}; echo $? > {shlex.quote(str(exit_code_file))}"
        )
        script_command = (
            f"script -q {shlex.quote(str(output_log))} -c {shlex.quote(wrapped_command)}"
        )

        logger.info(f"Creating rejoinable tmux session: {session}")
        logger.debug(f"  session_dir: {session_dir}")
        logger.debug(f"  output_log: {output_log}")
        logger.debug(f"  inner command: {inner_command}")

        print_info(
            f"Running smithers in tmux session '{session}' so you can reattach if disconnected."
        )
        console.print("Reconnect anytime with: [cyan]smithers rejoin[/cyan]")
        console.print()
        self._record_last_session_hint(session=session, command=inner_command)

        # Create detached tmux session
        self._create_detached_session(session, script_command)

        # Stream output to console
        exit_code = self._stream_session_output(session, output_log, exit_code_file)

        raise SystemExit(exit_code)

    def _get_session_dir(self, session: str) -> Path:
        """Get or create the directory for a session's output files.

        Args:
            session: The sanitized session name

        Returns:
            Path to the session directory
        """
        session_dir = DEFAULT_SESSIONS_DIR / session
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _create_detached_session(self, session: str, command: str) -> None:
        """Create a detached tmux session running the given command.

        Args:
            session: Session name (already sanitized)
            command: Command to run in the session

        Raises:
            TmuxError: If session creation fails
        """
        tmux_cmd = [
            "tmux",
            "new-session",
            "-d",  # Detached
            "-s",
            session,
            command,
        ]

        logger.debug(f"Creating detached tmux session: {' '.join(tmux_cmd)}")

        try:
            result = subprocess.run(
                tmux_cmd,
                capture_output=True,
                check=True,
                text=True,
            )
            log_subprocess_result(logger, tmux_cmd, result.returncode, result.stdout, result.stderr)
            logger.info(f"Detached tmux session '{session}' created successfully")
        except subprocess.CalledProcessError as e:
            log_subprocess_result(logger, tmux_cmd, e.returncode, e.stdout, e.stderr, success=False)
            logger.exception(f"Failed to create tmux session '{session}': {e.stderr}")
            raise TmuxError(f"Failed to create tmux session '{session}': {e.stderr}") from e

    def _stream_session_output(
        self,
        session: str,
        log_file: Path,
        exit_code_file: Path,
        poll_interval: float = 0.1,
    ) -> int:
        """Stream output from log file until session completes or user detaches.

        Args:
            session: The tmux session name
            log_file: Path to the output log file
            exit_code_file: Path to the exit code file
            poll_interval: Seconds between reads

        Returns:
            The exit code from the session (0 if detached by user)
        """
        detached = False

        def handle_sigint(_signum: int, _frame: object) -> None:
            nonlocal detached
            detached = True

        # Set up signal handler for graceful detach
        original_handler = signal.signal(signal.SIGINT, handle_sigint)

        try:
            # Wait for log file to be created (with timeout)
            wait_start = time.time()
            while not log_file.exists() and time.time() - wait_start < 5.0:
                if not self.session_exists(session):
                    logger.error(f"Session '{session}' exited before output was available")
                    return 1
                time.sleep(0.1)

            if not log_file.exists():
                logger.warning(f"Log file not created after 5s: {log_file}")
                # Fall back to waiting for session
                while self.session_exists(session) and not detached:
                    time.sleep(poll_interval)
                if detached:
                    print_detach_message(session)
                    return 0
                return self._read_exit_code(exit_code_file)

            # Stream the log file
            with log_file.open("rb") as f:
                while not detached:
                    data = f.read(4096)
                    if data:
                        # Write raw bytes to stdout to preserve ANSI codes
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    else:
                        # No new data - check if session is still running
                        if not self.session_exists(session):
                            # Session ended - read any remaining output
                            remaining = f.read()
                            if remaining:
                                sys.stdout.buffer.write(remaining)
                                sys.stdout.buffer.flush()
                            break
                        time.sleep(poll_interval)

            if detached:
                print_detach_message(session)
                return 0

            # Session completed - get exit code
            exit_code = self._read_exit_code(exit_code_file)
            print_session_complete(exit_code)
            return exit_code

        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, original_handler)

    def _read_exit_code(self, exit_code_file: Path) -> int:
        """Read the exit code from the marker file.

        Args:
            exit_code_file: Path to the exit code file

        Returns:
            The exit code, or 1 if not found
        """
        # Give a moment for the file to be written
        for _ in range(10):
            if exit_code_file.exists():
                try:
                    content = exit_code_file.read_text().strip()
                    if content.isdigit():
                        return int(content)
                except OSError:
                    pass
                break
            time.sleep(0.1)

        logger.warning(f"Could not read exit code from {exit_code_file}")
        return 1

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
        logger.info(f"Creating tmux session: name={session}, workdir={workdir}")
        logger.debug(f"  command: {command}")
        print_info(f"Starting tmux session '{session}' at {workdir}")

        tmux_cmd = [
            "tmux",
            "new-session",
            "-d",  # Detached
            "-s",
            session,
            "-c",
            str(workdir),
            command,
        ]

        try:
            result = subprocess.run(
                tmux_cmd,
                capture_output=True,
                check=True,
                text=True,
            )
            log_subprocess_result(logger, tmux_cmd, result.returncode, result.stdout, result.stderr)
            logger.info(f"Tmux session '{session}' created successfully")
        except subprocess.CalledProcessError as e:
            log_subprocess_result(logger, tmux_cmd, e.returncode, e.stdout, e.stderr, success=False)
            logger.exception(f"Failed to create tmux session '{session}': {e.stderr}")
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
        exists = result.returncode == 0
        logger.debug(f"session_exists({session}): {exists}")
        return exists

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
        logger.info(f"Waiting for {len(sessions)} sessions: {sessions}")

        console.print(f"Waiting for {len(sessions)} session(s) to complete...")

        iteration = 0
        with create_progress() as progress:
            task = progress.add_task(
                f"[cyan]Waiting for {len(remaining)} sessions...",
                total=None,
            )

            while remaining:
                iteration += 1
                still_running: list[str] = []
                for session in remaining:
                    if self.session_exists(session):
                        still_running.append(session)
                    else:
                        logger.info(f"Session '{session}' completed")
                        console.print(f"  [green]Session '{session}' completed[/green]")

                remaining = still_running

                if remaining:
                    logger.debug(
                        f"Wait iteration {iteration}: {len(remaining)} sessions still running"
                    )
                    shown = ", ".join(remaining[:3])
                    suffix = "..." if len(remaining) > 3 else ""
                    progress.update(
                        task,
                        description=f"[cyan]Waiting for {len(remaining)} sessions: {shown}{suffix}",
                    )
                    time.sleep(poll_interval)

        logger.info("All sessions completed")
        console.print("[green]All sessions completed[/green]")

    def kill_session(self, name: str) -> None:
        """Kill a tmux session if it exists.

        Args:
            name: Session name (will be sanitized)
        """
        session = self.sanitize_session_name(name)
        logger.debug(f"Killing tmux session: {session}")
        result = subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            logger.debug(f"Session '{session}' killed successfully")
        else:
            logger.debug(f"Session '{session}' kill returned {result.returncode} (may not exist)")

    def kill_all_smithers_sessions(self) -> None:
        """Kill all tmux sessions that appear to be smithers-related."""
        logger.info("Killing all smithers-related tmux sessions")
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                check=True,
                text=True,
            )
            sessions = result.stdout.strip().split("\n")
            logger.debug(f"Found {len(sessions)} tmux sessions")

            for session_name in sessions:
                name = session_name.strip()
                if not name:
                    continue
                # Kill sessions that look like branch names (start with letter, not just numbers)
                if name[0].isalpha() and not name.isdigit():
                    logger.debug(f"Killing session: {name}")
                    self.kill_session(name)
        except subprocess.CalledProcessError:
            logger.debug("No tmux sessions found or tmux not running")

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
