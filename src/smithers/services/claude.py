"""Claude CLI service for AI-powered code generation."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smithers.console import print_info
from smithers.exceptions import ClaudeError, DependencyMissingError
from smithers.logging_config import get_logger, log_subprocess_result

logger = get_logger("smithers.services.claude")


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
            digits = re.search(r"\d+", value)
            if digits:
                return int(digits.group())
        return None

    def extract_json(self) -> dict[str, Any] | None:
        """Extract structured JSON from the output.

        Looks for a JSON block delimited by ---JSON_OUTPUT--- and ---END_JSON---.

        Returns:
            Parsed JSON as a dict, or None if not found or invalid
        """
        pattern = r"---JSON_OUTPUT---\s*(\{.*?\})\s*---END_JSON---"
        match = re.search(pattern, self.output, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None

    def extract_pr_number(self) -> int | None:
        """Extract a PR number from the output using multiple strategies.

        Tries the following in order:
        1. Structured JSON output with pr_number field
        2. Common patterns like "PR #123", "pull request #123", "Created PR #123"
        3. GitHub PR URL patterns

        Returns:
            The PR number if found, None otherwise
        """
        # Strategy 1: Try structured JSON first
        json_output = self.extract_json()
        if json_output:
            pr_num = json_output.get("pr_number")
            if pr_num is not None:
                return int(pr_num)

        # Strategy 2: Look for common PR reference patterns
        # Match patterns like "PR #123", "pull request #123", "Created PR #123"
        pr_patterns = [
            r"(?:PR|Pull Request|pull request|Created PR|Opened PR|merged PR)\s*#(\d+)",
            r"(?:PR|Pull Request|pull request)\s+(\d+)",
            r"#(\d+)\s+(?:created|opened|merged)",
        ]
        for pattern in pr_patterns:
            match = re.search(pattern, self.output, re.IGNORECASE)
            if match:
                return int(match.group(1))

        # Strategy 3: Look for GitHub PR URL patterns
        # Match patterns like "github.com/owner/repo/pull/123"
        url_pattern = r"github\.com/[^/]+/[^/]+/pull/(\d+)"
        match = re.search(url_pattern, self.output)
        if match:
            return int(match.group(1))

        return None


@dataclass
class ClaudeService:
    """Service for invoking the Claude CLI."""

    model: str = "claude-opus-4-5-20251101"
    dangerously_skip_permissions: bool = True
    auto_compact: bool = False

    def check_dependencies(self) -> list[str]:
        """Check for required dependencies and return list of missing ones."""
        logger.debug("Checking claude CLI dependencies")
        missing: list[str] = []

        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                check=True,
                text=True,
            )
            logger.debug(f"claude CLI version: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("claude CLI not found or not working")
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
        auto_compact: bool | None = None,
    ) -> ClaudeResult:
        """Run a prompt through Claude CLI.

        Args:
            prompt: The prompt to send to Claude
            workdir: Optional working directory
            auto_compact: Override instance auto_compact setting if provided

        Returns:
            ClaudeResult with output and status

        Raises:
            ClaudeError: If the Claude CLI fails
        """
        cmd = ["claude", "--model", self.model, "--print"]

        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        # Use parameter override if provided, otherwise use instance setting
        use_auto_compact = auto_compact if auto_compact is not None else self.auto_compact
        if use_auto_compact:
            cmd.append("--auto-compact")

        logger.info(
            f"Running Claude prompt: model={self.model}, workdir={workdir}, "
            f"auto_compact={use_auto_compact}"
        )
        logger.debug(f"Claude command: {' '.join(cmd)}")
        logger.debug(f"Prompt (first 500 chars): {prompt[:500]}...")
        logger.debug(f"Prompt length: {len(prompt)} chars")

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

            success = result.returncode == 0
            output = result.stdout + result.stderr
            logger.info(f"Claude completed: exit_code={result.returncode}, success={success}")
            log_subprocess_result(
                logger, cmd, result.returncode, result.stdout, result.stderr, success=success
            )

            return ClaudeResult(
                output=output,
                exit_code=result.returncode,
                success=success,
            )
        except subprocess.SubprocessError as e:
            logger.exception("Failed to run Claude CLI")
            raise ClaudeError(f"Failed to run Claude CLI: {e}") from e

    def create_tmux_command(
        self,
        prompt_file: Path,
        output_file: Path,
        exit_file: Path,
        stream_log_file: Path | None = None,
    ) -> str:
        """Create a shell command for running Claude in tmux.

        The command pipes the prompt file to Claude and captures output.
        Uses streaming JSON output for real-time progress visibility.

        Args:
            prompt_file: Path to the file containing the prompt
            output_file: Path where the final text output will be written
            exit_file: Path where exit code will be written
            stream_log_file: Optional path for raw JSON stream log (for debugging)

        Returns:
            Shell command string for tmux
        """
        # Build the claude command with streaming JSON output
        claude_cmd_parts = [
            "claude",
            "--model",
            self.model,
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
        ]

        if self.dangerously_skip_permissions:
            claude_cmd_parts.append("--dangerously-skip-permissions")

        claude_cmd = " ".join(claude_cmd_parts)

        # If stream log file is provided, use tee to capture raw JSON stream
        if stream_log_file:
            # Pipe through tee to capture raw stream, then write to output file
            command = (
                f"cat '{prompt_file}' | {claude_cmd} "
                f"| tee '{stream_log_file}' > '{output_file}' 2>&1 ; "
                f"echo $? > '{exit_file}'"
            )
        else:
            # Just write to output file
            command = (
                f"cat '{prompt_file}' | {claude_cmd} > '{output_file}' 2>&1 ; "
                f"echo $? > '{exit_file}'"
            )

        logger.debug(f"Created tmux command for Claude: {command}")
        logger.debug(f"  prompt_file: {prompt_file}")
        logger.debug(f"  output_file: {output_file}")
        logger.debug(f"  exit_file: {exit_file}")
        if stream_log_file:
            logger.debug(f"  stream_log_file: {stream_log_file}")

        return command

    def parse_stream_json_output(self, output: str) -> str:
        """Extract the final text result from stream-json output.

        The stream-json format outputs one JSON object per line with types:
        - {"type": "system", ...} - initialization info
        - {"type": "assistant", "message": {...}} - assistant messages
        - {"type": "result", "result": "...", ...} - final result

        Args:
            output: The raw stream-json output (multiple JSON lines)

        Returns:
            The extracted text result, or the original output if parsing fails
        """
        lines = output.strip().split("\n")

        # Try to find the result line (usually the last one)
        for raw_line in reversed(lines):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("type") == "result" and "result" in data:
                    result = data["result"]
                    logger.debug(f"Extracted result from stream-json ({len(result)} chars)")
                    return result
            except json.JSONDecodeError:
                continue

        # Fallback: try to extract from assistant messages
        assistant_texts: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("type") == "assistant":
                    message = data.get("message", {})
                    content = message.get("content", [])
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            assistant_texts.append(block.get("text", ""))
            except json.JSONDecodeError:
                continue

        if assistant_texts:
            result = "\n".join(assistant_texts)
            logger.debug(f"Extracted text from assistant messages ({len(result)} chars)")
            return result

        # Final fallback: return original output
        logger.warning("Could not parse stream-json output, returning raw output")
        return output

    def get_stream_stats(self, output: str) -> dict[str, Any]:
        """Extract statistics from stream-json output.

        Args:
            output: The raw stream-json output

        Returns:
            Dictionary with stats like cost, tokens, duration, etc.
        """
        stats: dict[str, Any] = {}
        lines = output.strip().split("\n")

        for raw_line in reversed(lines):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("type") == "result":
                    stats["duration_ms"] = data.get("duration_ms")
                    stats["duration_api_ms"] = data.get("duration_api_ms")
                    stats["num_turns"] = data.get("num_turns")
                    stats["total_cost_usd"] = data.get("total_cost_usd")
                    stats["is_error"] = data.get("is_error", False)
                    stats["usage"] = data.get("usage")
                    break
            except json.JSONDecodeError:
                continue

        return stats
