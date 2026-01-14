"""GitHub CLI service for PR and repository operations."""

import json
import subprocess
from dataclasses import dataclass

from smithers.exceptions import DependencyMissingError, GitHubError


@dataclass
class PRInfo:
    """Information about a pull request."""

    number: int
    title: str
    branch: str
    state: str
    url: str


@dataclass
class CheckStatus:
    """Status of a CI/CD check."""

    name: str
    status: str  # "pass", "fail", "pending"
    conclusion: str | None


@dataclass
class ReviewComment:
    """A review comment on a PR."""

    id: str
    author: str
    body: str
    path: str | None
    line: int | None
    is_resolved: bool


@dataclass
class GitHubService:
    """Service for GitHub CLI (gh) operations."""

    def _get_repo_info(self) -> tuple[str, str]:
        """Get owner and repo name from current git repository.

        Returns:
            Tuple of (owner, repo_name)

        Raises:
            GitHubError: If unable to determine repo info
        """
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "owner,name"],
                capture_output=True,
                check=True,
                text=True,
            )
            data = json.loads(result.stdout)
            return data["owner"]["login"], data["name"]
        except subprocess.CalledProcessError as e:
            raise GitHubError(f"Failed to get repo info: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise GitHubError(f"Failed to parse repo info: {e}") from e

    def check_dependencies(self) -> list[str]:
        """Check for required dependencies and return list of missing ones."""
        missing: list[str] = []

        try:
            subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("gh (GitHub CLI)")

        return missing

    def ensure_dependencies(self) -> None:
        """Ensure all required dependencies are installed."""
        missing = self.check_dependencies()
        if missing:
            raise DependencyMissingError(missing)

    def get_pr_info(self, pr_number: int) -> PRInfo:
        """Get information about a pull request.

        Args:
            pr_number: The PR number

        Returns:
            PRInfo with PR details

        Raises:
            GitHubError: If the operation fails
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "number,title,headRefName,state,url",
                ],
                capture_output=True,
                check=True,
                text=True,
            )
            data = json.loads(result.stdout)
            return PRInfo(
                number=data["number"],
                title=data["title"],
                branch=data["headRefName"],
                state=data["state"],
                url=data["url"],
            )
        except subprocess.CalledProcessError as e:
            raise GitHubError(f"Failed to get PR #{pr_number} info: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise GitHubError(f"Failed to parse PR #{pr_number} info: {e}") from e

    def get_pr_branch(self, pr_number: int) -> str:
        """Get the branch name for a PR.

        Args:
            pr_number: The PR number

        Returns:
            The branch name
        """
        return self.get_pr_info(pr_number).branch

    def get_pr_checks(self, pr_number: int) -> list[CheckStatus]:
        """Get CI/CD check status for a PR.

        Args:
            pr_number: The PR number

        Returns:
            List of check statuses
        """
        try:
            result = subprocess.run(
                ["gh", "pr", "checks", str(pr_number), "--json", "name,state,conclusion"],
                capture_output=True,
                check=True,
                text=True,
            )
            data = json.loads(result.stdout)
            return [
                CheckStatus(
                    name=check.get("name", ""),
                    status=check.get("state", "pending"),
                    conclusion=check.get("conclusion"),
                )
                for check in data
            ]
        except subprocess.CalledProcessError:
            return []
        except json.JSONDecodeError:
            return []

    def all_checks_passing(self, pr_number: int) -> bool:
        """Check if all CI/CD checks are passing.

        Args:
            pr_number: The PR number

        Returns:
            True if all checks pass
        """
        checks = self.get_pr_checks(pr_number)
        if not checks:
            return True  # No checks configured

        return all(check.status == "pass" or check.conclusion == "success" for check in checks)

    def get_unresolved_comments(self, pr_number: int) -> list[ReviewComment]:
        """Get unresolved review comments on a PR.

        Uses GraphQL to get thread resolution status.

        Args:
            pr_number: The PR number

        Returns:
            List of unresolved review comments
        """
        # Get owner/repo dynamically from current repository
        owner, repo = self._get_repo_info()

        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              reviewThreads(first: 100) {
                nodes {
                  isResolved
                  comments(first: 10) {
                    nodes {
                      id
                      author { login }
                      body
                      path
                      line
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            result = subprocess.run(
                [
                    "gh",
                    "api",
                    "graphql",
                    "-f",
                    f"query={query}",
                    "-F",
                    f"owner={owner}",
                    "-F",
                    f"repo={repo}",
                    "-F",
                    f"number={pr_number}",
                ],
                capture_output=True,
                check=True,
                text=True,
            )
            data = json.loads(result.stdout)

            comments: list[ReviewComment] = []
            threads = (
                data.get("data", {})
                .get("repository", {})
                .get("pullRequest", {})
                .get("reviewThreads", {})
                .get("nodes", [])
            )

            for thread in threads:
                is_resolved = thread.get("isResolved", False)
                for comment in thread.get("comments", {}).get("nodes", []):
                    comments.append(
                        ReviewComment(
                            id=comment.get("id", ""),
                            author=comment.get("author", {}).get("login", "unknown"),
                            body=comment.get("body", ""),
                            path=comment.get("path"),
                            line=comment.get("line"),
                            is_resolved=is_resolved,
                        )
                    )

            # Filter to only unresolved
            return [c for c in comments if not c.is_resolved]
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return []

    def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False,
    ) -> int:
        """Create a pull request.

        Args:
            title: PR title
            body: PR body/description
            base: Base branch
            draft: Whether to create as draft

        Returns:
            The created PR number

        Raises:
            GitHubError: If PR creation fails
        """
        cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        ]

        if draft:
            cmd.append("--draft")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                text=True,
            )
            # gh pr create outputs the PR URL, extract number from it
            url = result.stdout.strip()
            # URL format: https://github.com/org/repo/pull/123
            pr_number = int(url.split("/")[-1])
            return pr_number
        except subprocess.CalledProcessError as e:
            raise GitHubError(f"Failed to create PR: {e.stderr}") from e
        except (ValueError, IndexError) as e:
            raise GitHubError(f"Failed to parse PR number from output: {e}") from e
