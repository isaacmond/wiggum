"""Tmux session management service."""

import contextlib
import os
import platform
import selectors
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Callable
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

        # Check tmux
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

        # Check script (used for capturing terminal output)
        # script is part of util-linux on Linux and bsdmainutils on macOS
        try:
            result = subprocess.run(
                ["which", "script"],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.debug(f"script found at: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("script command not found")
            missing.append("script")

        return missing

    def _has_caffeinate(self) -> bool:
        """Check if caffeinate is available (macOS built-in command).

        caffeinate prevents the system from sleeping while a process runs.
        It's a standard macOS utility and not available on Linux.

        Returns:
            True if caffeinate is available, False otherwise.
        """
        if platform.system() != "Darwin":
            return False
        try:
            result = subprocess.run(
                ["which", "caffeinate"],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.debug(f"caffeinate found at: {result.stdout.strip()}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug("caffeinate not found")
            return False

    def _wrap_with_caffeinate(self, command: str) -> str:
        """Wrap a command with caffeinate to prevent system sleep.

        Uses caffeinate -dims to prevent:
        - Display sleep (-d)
        - System idle sleep (-i)
        - Disk idle sleep (-m)
        - System sleep when on AC power (-s)

        Args:
            command: The command to wrap

        Returns:
            The command wrapped with caffeinate if available, otherwise unchanged.
        """
        if not self._has_caffeinate():
            return command
        # Use caffeinate -dims to prevent all types of sleep
        # -w is not used as we want caffeinate to run for the full session duration
        logger.debug("Wrapping command with caffeinate -dims")
        return f"caffeinate -dims /bin/sh -c {shlex.quote(command)}"

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

        # Handle existing session - kill it for a fresh start
        # Users who want to resume should use 'smithers rejoin'
        if self.session_exists(session):
            logger.info(f"Session '{session}' already exists, killing for fresh start")
            print_info(f"Killing existing session '{session}' (use 'smithers rejoin' to resume)")
            self.kill_session(session)

        session_dir = self._get_session_dir(session)
        output_log = session_dir / "output.log"
        exit_code_file = session_dir / "exit_code"

        # Build the inner command with script wrapper
        inner_command = " ".join(shlex.quote(arg) for arg in argv)
        # Use script to capture terminal output to a file.
        # Always write an exit code marker on shell EXIT so the wrapper
        # can report a stable status even if the session is interrupted.
        exit_code_var = shlex.quote(str(exit_code_file))
        wrapped_command = (
            f"EXIT_CODE_FILE={exit_code_var}; "
            'trap \'mkdir -p "$(dirname "$EXIT_CODE_FILE")"; '
            'echo $? > "$EXIT_CODE_FILE"\' EXIT; '
            f"SMITHERS_TMUX_WRAPPED=1 {inner_command}"
        )
        # macOS (BSD) and Linux (GNU) have different script command syntax:
        # - Linux (util-linux): script -q -f FILE -c "COMMAND" (-f flushes after each write)
        # - macOS (BSD): script -q -F FILE COMMAND... (-F flushes after each write)
        # Both Intel and ARM Macs use the same BSD script command.
        script_command = self._build_script_command(output_log, wrapped_command)

        logger.info(f"Creating rejoinable tmux session: {session}")
        logger.debug(f"  session_dir: {session_dir}")
        logger.debug(f"  output_log: {output_log}")
        logger.debug(f"  inner command: {inner_command}")

        print_info(
            f"Running smithers in tmux session '{session}' so you can reattach if disconnected."
        )
        console.print("[dim]Press Ctrl+C to detach without stopping the session[/dim]")
        console.print("[dim]Reconnect anytime with:[/dim] [cyan]smithers rejoin[/cyan]")
        console.print()
        # Flush stdout to ensure messages appear before we enter the streaming loop
        sys.stdout.flush()
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

    def _build_script_command(self, output_log: Path, wrapped_command: str) -> str:
        """Build the platform-specific script command for capturing terminal output.

        Handles differences between:
        - macOS (BSD script): Works on both Intel and ARM Macs
        - Linux (util-linux script): Works on most Linux distributions

        Args:
            output_log: Path to the output log file
            wrapped_command: The command to run inside script

        Returns:
            The complete script command string
        """
        log_path = shlex.quote(str(output_log))
        cmd = shlex.quote(wrapped_command)

        if platform.system() == "Darwin":
            # macOS (BSD) script: script [-q] [-F] file command [arguments ...]
            # -q: quiet mode (don't print start/end messages)
            # -F: flush output after each write (macOS 10.15+, fall back without if needed)
            # Works identically on Intel (x86_64) and ARM (arm64) Macs
            return f"script -q -F {log_path} /bin/sh -c {cmd}"

        # Linux (util-linux) script: script [options] [file [command [arguments]]]
        # -q: quiet mode
        # -f: flush output after each write (util-linux 2.25+, 2014)
        # -c: run command (required on Linux, command is passed as argument to -c)
        return f"script -q -f {log_path} -c {cmd}"

    def _create_detached_session(self, session: str, command: str) -> None:
        """Create a detached tmux session running the given command.

        The command is wrapped with caffeinate on macOS to prevent system sleep.

        Args:
            session: Session name (already sanitized)
            command: Command to run in the session

        Raises:
            TmuxError: If session creation fails
        """
        # Defensive check: ensure no duplicate session exists
        if self.session_exists(session):
            logger.warning(f"Session '{session}' exists in _create_detached_session, killing")
            self.kill_session(session)

        # Wrap command with caffeinate to prevent system sleep on macOS
        wrapped_command = self._wrap_with_caffeinate(command)

        tmux_cmd = [
            "tmux",
            "new-session",
            "-d",  # Detached
            "-s",
            session,
            wrapped_command,
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
        exit_check_interval: float = 0.1,
        fallback_session_check_interval: float = 10.0,
    ) -> int:
        """Stream output from log file until session completes or user detaches.

        Uses `tail -f` for efficient real-time streaming with minimal latency.
        Detects session completion by watching for exit_code_file to appear,
        avoiding expensive subprocess calls.

        Args:
            session: The tmux session name
            log_file: Path to the output log file
            exit_code_file: Path to the exit code file
            exit_check_interval: Seconds between exit file checks (cheap file stat)
            fallback_session_check_interval: Seconds between tmux session checks
                (expensive subprocess, fallback only)

        Returns:
            The exit code from the session (0 if detached by user)
        """
        detached = False
        tail_proc: subprocess.Popen[bytes] | None = None

        # Remove stale exit code file from previous runs
        with contextlib.suppress(OSError):
            exit_code_file.unlink(missing_ok=True)

        def handle_sigint(_signum: int, _frame: object) -> None:
            nonlocal detached
            detached = True

        # Set up signal handler for graceful detach
        original_handler = signal.signal(signal.SIGINT, handle_sigint)

        try:
            # Wait for log file to be created (with timeout)
            wait_start = time.time()
            while not log_file.exists() and time.time() - wait_start < 5.0:
                # Check exit_code_file first (cheap), then session (expensive) as fallback
                if exit_code_file.exists() or not self.session_exists(session):
                    logger.error(f"Session '{session}' exited before output was available")
                    return self._read_exit_code(exit_code_file) if exit_code_file.exists() else 1
                time.sleep(0.05)

            if not log_file.exists():
                logger.warning(f"Log file not created after 5s: {log_file}")
                # Fall back to waiting for session via file-based detection
                while not exit_code_file.exists() and not detached:
                    time.sleep(exit_check_interval)
                if detached:
                    print_detach_message(session)
                    return 0
                return self._read_exit_code(exit_code_file)

            # Use tail -f for efficient streaming
            # -n +1 starts from line 1 (beginning of file)
            tail_proc = subprocess.Popen(
                ["tail", "-f", "-n", "+1", str(log_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            # Set pipe to non-blocking mode to prevent read() from blocking
            # even after select() indicates data is available
            stdout_fd = tail_proc.stdout.fileno()  # type: ignore[union-attr]
            os.set_blocking(stdout_fd, False)

            # Use selectors for non-blocking reads with timeout
            sel = selectors.DefaultSelector()
            sel.register(tail_proc.stdout, selectors.EVENT_READ)  # type: ignore[arg-type]

            last_exit_check = time.time()
            last_session_check = time.time()

            while not detached:
                # Wait for data with minimal timeout for low latency
                # 1ms is responsive enough for real-time streaming while avoiding busy-wait
                events = sel.select(timeout=0.001)

                for _key, _ in events:
                    # Use os.read() for truly non-blocking reads
                    # Large buffer (64KB) for high throughput when data is available
                    try:
                        data = os.read(stdout_fd, 65536)
                        if data:
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()
                    except BlockingIOError:
                        # No data available right now, continue
                        pass

                now = time.time()

                # Primary detection: check if exit_code_file exists (cheap file stat, no subprocess)
                if now - last_exit_check >= exit_check_interval:
                    last_exit_check = now
                    if exit_code_file.exists():
                        logger.debug("Exit code file detected, session complete")
                        # Session ended - drain any remaining output
                        self._drain_and_cleanup_tail(sel, tail_proc, stdout_fd)
                        tail_proc = None
                        break

                # Fallback detection: check tmux session (expensive subprocess, infrequent)
                # This handles edge cases where exit_code_file isn't written
                if now - last_session_check >= fallback_session_check_interval:
                    last_session_check = now
                    if not self.session_exists(session):
                        logger.debug("Tmux session no longer exists (fallback check)")
                        self._drain_and_cleanup_tail(sel, tail_proc, stdout_fd)
                        tail_proc = None
                        break

            sel.close()

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

            # Clean up tail process if still running
            if tail_proc is not None:
                tail_proc.terminate()
                try:
                    tail_proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    tail_proc.kill()
                    tail_proc.wait()

    def _drain_and_cleanup_tail(
        self,
        sel: selectors.BaseSelector,
        tail_proc: subprocess.Popen[bytes],
        stdout_fd: int,
    ) -> None:
        """Drain remaining output from tail and clean up.

        Args:
            sel: The selector watching tail's stdout
            tail_proc: The tail subprocess
            stdout_fd: File descriptor for tail's stdout
        """
        # Brief pause for final file writes
        time.sleep(0.05)

        # Drain any remaining buffered output
        try:
            while True:
                data = os.read(stdout_fd, 65536)
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
        except BlockingIOError:
            pass

        sel.unregister(tail_proc.stdout)  # type: ignore[arg-type]
        tail_proc.stdout.close()  # type: ignore[union-attr]
        tail_proc.terminate()
        tail_proc.wait()

    def _read_exit_code(self, exit_code_file: Path, max_wait: float = 5.0) -> int:
        """Read the exit code from the marker file.

        Args:
            exit_code_file: Path to the exit code file
            max_wait: Maximum seconds to wait for file to be readable

        Returns:
            The exit code, or 1 if not found
        """
        # Brief retry loop in case file was just created but not yet written
        start = time.time()
        while time.time() - start < max_wait:
            if exit_code_file.exists():
                try:
                    content = exit_code_file.read_text().strip()
                    if content.isdigit():
                        return int(content)
                    # File exists but content not yet valid, retry briefly
                except OSError:
                    pass
            time.sleep(0.01)  # 10ms between retries

        logger.warning(f"Could not read exit code from {exit_code_file}")
        return 1

    def create_session(
        self,
        name: str,
        workdir: Path,
        command: str,
    ) -> str:
        """Create a new tmux session running the given command.

        The command is wrapped with caffeinate on macOS to prevent system sleep.

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

        # Kill any existing session with this name (from interrupted runs)
        if self.session_exists(session):
            logger.info(f"Session '{session}' already exists from previous run, killing it")
            self.kill_session(session)

        print_info(f"Starting tmux session '{session}' at {workdir}")

        # Wrap command with caffeinate to prevent system sleep on macOS
        wrapped_command = self._wrap_with_caffeinate(command)

        tmux_cmd = [
            "tmux",
            "new-session",
            "-d",  # Detached
            "-s",
            session,
            "-c",
            str(workdir),
            wrapped_command,
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
        on_session_complete: Callable[[str], None] | None = None,
    ) -> None:
        """Wait for multiple tmux sessions to complete.

        Args:
            sessions: List of session names to wait for
            poll_interval: Seconds between status checks
            on_session_complete: Optional callback invoked when each session completes.
                                 Called with the session name as argument.
        """
        remaining = list(sessions)
        logger.info(f"Waiting for {len(sessions)} sessions: {sessions}")

        console.print(f"Waiting for {len(sessions)} session(s) to complete...")

        iteration = 0
        try:
            with create_progress() as progress:
                task = progress.add_task(
                    f"[cyan]Waiting for {len(remaining)} sessions...",
                    total=None,
                )

                while remaining:
                    iteration += 1
                    still_running: list[str] = []
                    for session in remaining:
                        try:
                            if self.session_exists(session):
                                still_running.append(session)
                            else:
                                logger.info(f"Session '{session}' completed")
                                console.print(f"  [green]Session '{session}' completed[/green]")
                                # Call completion callback immediately
                                if on_session_complete is not None:
                                    try:
                                        on_session_complete(session)
                                    except Exception as cb_err:
                                        logger.warning(
                                            f"on_session_complete callback failed for "
                                            f"'{session}': {cb_err}"
                                        )
                        except Exception as e:
                            logger.exception("Error checking session '%s'", session)
                            # Assume session is done if we can't check it
                            console.print(
                                f"  [yellow]Session '{session}' check failed: {e}[/yellow]"
                            )

                    remaining = still_running

                    if remaining:
                        logger.debug(
                            f"Wait iteration {iteration}: {len(remaining)} sessions still running"
                        )
                        shown = ", ".join(remaining[:3])
                        suffix = "..." if len(remaining) > 3 else ""
                        progress.update(
                            task,
                            description=f"[cyan]Waiting for {len(remaining)}: {shown}{suffix}",
                        )
                        time.sleep(poll_interval)

            logger.info("All sessions completed")
            console.print("[green]All sessions completed[/green]")
        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt during session wait")
            console.print("[yellow]Interrupted while waiting for sessions[/yellow]")
            raise
        except Exception as e:
            logger.exception("Unexpected error during session wait")
            console.print(f"[red]Error waiting for sessions: {e}[/red]")
            raise

    def kill_session(self, name: str, wait_for_cleanup: bool = True) -> None:
        """Kill a tmux session if it exists.

        Args:
            name: Session name (will be sanitized)
            wait_for_cleanup: If True, wait for session to be fully cleaned up
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
            # Wait for tmux to fully clean up the session to avoid race conditions
            # when creating a new session with the same name
            if wait_for_cleanup:
                for _ in range(10):  # Up to 0.5 seconds
                    if not self.session_exists(session):
                        break
                    time.sleep(0.05)
        else:
            logger.debug(f"Session '{session}' kill returned {result.returncode} (may not exist)")

    def kill_all_smithers_sessions(self, exclude_parent: bool = True) -> None:
        """Kill all tmux sessions that appear to be smithers worker sessions.

        Args:
            exclude_parent: If True, don't kill parent sessions (smithers-fix-*, smithers-impl-*).
                           These are the main sessions that run the fix/implement commands.
        """
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
                # Never kill parent smithers sessions - these are the main sessions
                # running the fix/implement commands
                if exclude_parent and name.startswith(("smithers-fix-", "smithers-impl-")):
                    logger.debug(f"Skipping parent session: {name}")
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
        """Attach to an existing tmux session (raw tmux attach).

        This gives full terminal control but uses Ctrl+B D to detach.

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

    def get_session_worktrees(self, session: str) -> list[str]:
        """Get worktrees tracked for a session.

        Args:
            session: The sanitized session name

        Returns:
            List of branch names for tracked worktrees
        """
        session = self.sanitize_session_name(session)
        session_dir = DEFAULT_SESSIONS_DIR / session
        worktrees_file = session_dir / "worktrees.txt"
        if not worktrees_file.exists():
            return []
        try:
            content = worktrees_file.read_text().strip()
            return [b for b in content.split("\n") if b]
        except OSError:
            return []

    def get_session_prs(self, session: str) -> list[int]:
        """Get PR numbers tracked for a session.

        PRs are tracked by Claude writing to prs.txt during implementation.

        Args:
            session: The sanitized session name

        Returns:
            List of PR numbers tracked for this session
        """
        session = self.sanitize_session_name(session)
        session_dir = DEFAULT_SESSIONS_DIR / session
        prs_file = session_dir / "prs.txt"
        if not prs_file.exists():
            return []
        try:
            content = prs_file.read_text().strip()
            prs: list[int] = []
            for raw_line in content.split("\n"):
                stripped = raw_line.strip()
                if stripped and stripped.isdigit():
                    prs.append(int(stripped))
            return prs
        except OSError:
            return []

    @staticmethod
    def get_session_mode(session: str) -> str | None:
        """Detect the mode of a session from its name.

        Args:
            session: The session name

        Returns:
            "implement" for smithers-impl-* sessions,
            "fix" for smithers-fix-* sessions,
            None for unknown session types
        """
        if session.startswith("smithers-impl-"):
            return "implement"
        if session.startswith("smithers-fix-"):
            return "fix"
        return None

    @staticmethod
    def get_session_design_doc_stem(session: str) -> str | None:
        """Extract the design doc stem from a session name.

        Args:
            session: The session name

        Returns:
            The design doc stem (e.g., "notes" from "smithers-impl-notes"),
            or None if not an implement session
        """
        if session.startswith("smithers-impl-"):
            return session[len("smithers-impl-") :]
        return None

    def get_session_plan_files(self, session: str) -> list[Path]:
        """Get plan files associated with a session.

        Plan files are stored in ~/.smithers/plans/ with names like:
        {design_doc_stem}.smithers-{timestamp}.md

        Args:
            session: The session name

        Returns:
            List of plan file paths matching this session
        """
        stem = self.get_session_design_doc_stem(session)
        if not stem:
            return []

        plans_dir = Path.home() / ".smithers" / "plans"
        if not plans_dir.exists():
            return []

        # Find all plan files matching this design doc stem
        pattern = f"{stem}.smithers-*.md"
        return sorted(plans_dir.glob(pattern))
