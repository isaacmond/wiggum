"""Claude CLI service for AI-powered code generation."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from wiggum.console import print_info
from wiggum.exceptions import ClaudeError, DependencyMissingError


@dataclass
class ClaudeResult:
    """Result from a Claude CLI invocation."""

    output: str
    exit_code: int
    success: bool

    def extract_value(self, key: str) -> str | None:
        """Extract a value from the output in format 'KEY: value'.

        Args:
            key: The key to search for

        Returns:
            The value if found, None otherwise
        """
        import re

        pattern = rf"{re.escape(key)}:\s*(\S+)"
        match = re.search(pattern, self.output)
        return match.group(1) if match else None

    def extract_int(self, key: str) -> int | None:
        """Extract an integer value from the output.

        Args:
            key: The key to search for

        Returns:
            The integer value if found, None otherwise
        """
        value = self.extract_value(key)
        if value:
            # Extract just the digits
            import re

            digits = re.search(r"\d+", value)
            if digits:
                return int(digits.group())
        return None

    def has_flag(self, flag: str) -> bool:
        """Check if a flag is set to true in the output.

        Args:
            flag: The flag to check (e.g., "ALL_DONE")

        Returns:
            True if the flag is set to true
        """
        value = self.extract_value(flag)
        return value is not None and value.lower() == "true"


@dataclass
class ClaudeService:
    """Service for invoking the Claude CLI."""

    model: str = "claude-opus-4-5-20251101"
    dangerously_skip_permissions: bool = True

    def check_dependencies(self) -> list[str]:
        """Check for required dependencies and return list of missing ones."""
        missing: list[str] = []

        try:
            subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("claude")

        return missing

    def ensure_dependencies(self) -> None:
        """Ensure all required dependencies are installed."""
        missing = self.check_dependencies()
        if missing:
            raise DependencyMissingError(missing)

    def run_prompt(
        self,
        prompt: str,
        workdir: Path | None = None,
    ) -> ClaudeResult:
        """Run a prompt through Claude CLI.

        Args:
            prompt: The prompt to send to Claude
            workdir: Optional working directory

        Returns:
            ClaudeResult with output and status

        Raises:
            ClaudeError: If the Claude CLI fails
        """
        cmd = ["claude", "--model", self.model, "--print"]

        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        print_info(f"Running Claude with model: {self.model}")

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=workdir,
                check=False,
            )

            return ClaudeResult(
                output=result.stdout + result.stderr,
                exit_code=result.returncode,
                success=result.returncode == 0,
            )
        except subprocess.SubprocessError as e:
            raise ClaudeError(f"Failed to run Claude CLI: {e}") from e

    def create_tmux_command(
        self,
        prompt_file: Path,
        output_file: Path,
        exit_file: Path,
    ) -> str:
        """Create a shell command for running Claude in tmux.

        The command pipes the prompt file to Claude and captures output.

        Args:
            prompt_file: Path to the file containing the prompt
            output_file: Path where stdout/stderr will be written
            exit_file: Path where exit code will be written

        Returns:
            Shell command string for tmux
        """
        cmd_parts = [
            f"cat '{prompt_file}'",
            "|",
            "claude",
            "--model",
            self.model,
            "--print",
        ]

        if self.dangerously_skip_permissions:
            cmd_parts.append("--dangerously-skip-permissions")

        cmd_parts.extend(
            [
                f"> '{output_file}' 2>&1",
                ";",
                f"echo $? > '{exit_file}'",
            ]
        )

        return " ".join(cmd_parts)
