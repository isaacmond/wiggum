"""Git and worktree management service."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from smithers.console import print_info, print_warning
from smithers.exceptions import DependencyMissingError, WorktreeError


@dataclass
class GitService:
    """Service for Git and worktree operations using gtr (git-worktree-runner)."""

    created_worktrees: list[str] = field(default_factory=list)

    def check_dependencies(self) -> list[str]:
        """Check for required dependencies and return list of missing ones."""
        missing: list[str] = []

        # Check git
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("git")

        # Check gtr (git-worktree-runner)
        try:
            subprocess.run(
                ["git", "gtr", "version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("git-worktree-runner (gtr)")

        return missing

    def ensure_dependencies(self) -> None:
        """Ensure all required dependencies are installed."""
        missing = self.check_dependencies()
        if missing:
            raise DependencyMissingError(missing)

    def create_worktree(self, branch: str, base: str = "main") -> Path:
        """Create a worktree for the given branch, or return existing one.

        Args:
            branch: The branch name for the new worktree
            base: The base ref to create the branch from

        Returns:
            Path to the created or existing worktree

        Raises:
            WorktreeError: If worktree creation fails
        """
        # Check if worktree already exists
        existing_path = self.get_worktree_path(branch)
        if existing_path is not None:
            print_info(f"Using existing worktree for branch: {branch} at {existing_path}")
            # Track for cleanup if not already tracked
            if branch not in self.created_worktrees:
                self.created_worktrees.append(branch)
            return existing_path

        print_info(f"Creating worktree for branch: {branch} (from {base})")

        try:
            subprocess.run(
                ["git", "gtr", "new", branch, "--from", base, "--yes"],
                capture_output=True,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise WorktreeError(f"Failed to create worktree for {branch}: {e.stderr}") from e

        # Track for cleanup
        self.created_worktrees.append(branch)

        # Get the worktree path
        worktree_path = self.get_worktree_path(branch)
        if worktree_path is None:
            raise WorktreeError(f"Worktree created but path not found for {branch}")

        return worktree_path

    def get_worktree_path(self, branch: str) -> Path | None:
        """Get the filesystem path for a worktree.

        Args:
            branch: The branch name

        Returns:
            Path to the worktree, or None if not found
        """
        try:
            result = subprocess.run(
                ["git", "gtr", "go", branch],
                capture_output=True,
                check=True,
                text=True,
            )
            path_str = result.stdout.strip()
            if path_str:
                return Path(path_str)
        except subprocess.CalledProcessError:
            pass
        return None

    def cleanup_worktree(self, branch: str) -> None:
        """Remove a worktree.

        Args:
            branch: The branch name of the worktree to remove
        """
        print_info(f"Cleaning up worktree for branch: {branch}")

        try:
            subprocess.run(
                ["git", "gtr", "rm", branch, "--yes"],
                capture_output=True,
                check=False,  # Don't raise on error
                text=True,
            )
        except subprocess.CalledProcessError:
            print_warning(f"Failed to cleanup worktree for {branch}")

        # Remove from tracking
        if branch in self.created_worktrees:
            self.created_worktrees.remove(branch)

    def cleanup_all_worktrees(self) -> None:
        """Remove all created worktrees."""
        for branch in list(self.created_worktrees):
            self.cleanup_worktree(branch)

    def get_branch_dependency_base(
        self,
        depends_on: str | None,
        default_base: str = "main",
    ) -> str:
        """Determine the base ref for a stage based on its dependencies.

        Args:
            depends_on: The dependency branch name (e.g., "stage-1-models") or None/"none"
            default_base: Default base if no dependency

        Returns:
            The base ref to use
        """
        if depends_on is None or depends_on.lower() == "none":
            return default_base

        # depends_on is now the actual branch name (no more "Stage N" parsing needed)
        return depends_on
