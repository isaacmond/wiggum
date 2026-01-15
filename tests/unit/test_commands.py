"""Unit tests for command utilities."""

import pytest

from smithers.utils.parsing import parse_pr_identifier


class TestParsePrIdentifier:
    """Tests for parse_pr_identifier function."""

    def test_parse_integer_string(self) -> None:
        """Test parsing a plain integer string."""
        assert parse_pr_identifier("123") == 123
        assert parse_pr_identifier("1") == 1
        assert parse_pr_identifier("99999") == 99999

    def test_parse_github_url(self) -> None:
        """Test parsing GitHub PR URLs."""
        assert parse_pr_identifier("https://github.com/owner/repo/pull/123") == 123
        assert parse_pr_identifier("https://github.com/Metaview/smithers/pull/42") == 42

    def test_parse_github_url_with_www(self) -> None:
        """Test parsing GitHub PR URLs with www prefix."""
        assert parse_pr_identifier("https://www.github.com/owner/repo/pull/456") == 456

    def test_parse_github_url_with_trailing_slash(self) -> None:
        """Test parsing GitHub PR URLs with trailing slash."""
        assert parse_pr_identifier("https://github.com/owner/repo/pull/789/") == 789

    def test_parse_github_url_with_extra_path(self) -> None:
        """Test parsing GitHub PR URLs with extra path segments."""
        assert parse_pr_identifier("https://github.com/owner/repo/pull/123/files") == 123
        assert parse_pr_identifier("https://github.com/owner/repo/pull/123/commits") == 123

    def test_invalid_string(self) -> None:
        """Test that invalid strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid PR identifier"):
            parse_pr_identifier("not-a-number")

    def test_invalid_url(self) -> None:
        """Test that non-GitHub URLs raise ValueError."""
        with pytest.raises(ValueError, match="Invalid PR identifier"):
            parse_pr_identifier("https://gitlab.com/owner/repo/merge_requests/123")

    def test_invalid_github_url_not_pr(self) -> None:
        """Test that GitHub URLs that aren't PRs raise ValueError."""
        with pytest.raises(ValueError, match="Invalid PR identifier"):
            parse_pr_identifier("https://github.com/owner/repo/issues/123")
        with pytest.raises(ValueError, match="Invalid PR identifier"):
            parse_pr_identifier("https://github.com/owner/repo")

    def test_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PR identifier"):
            parse_pr_identifier("")
