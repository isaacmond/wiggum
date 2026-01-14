"""Version checking service for wiggum."""

import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from wiggum import __version__
from wiggum.console import print_warning

# Cache settings
CACHE_DIR = Path.home() / ".wiggum"
VERSION_CACHE_FILE = CACHE_DIR / "version_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours

GITHUB_API_URL = "https://api.github.com/repos/isaacmond/wiggum/tags"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of integers for comparison."""
    # Handle versions like "0.2.1" -> (0, 2, 1)
    parts = []
    for part in version_str.split("."):
        # Strip any pre-release suffixes (e.g., "1.0.0a1" -> "1", "0", "0")
        numeric = ""
        for char in part:
            if char.isdigit():
                numeric += char
            else:
                break
        parts.append(int(numeric) if numeric else 0)
    return tuple(parts)


def _fetch_latest_version() -> str | None:
    """Fetch the latest version from GitHub tags."""
    try:
        # GitHub API requires a User-Agent header
        request = Request(GITHUB_API_URL, headers={"User-Agent": "wiggum-version-check"})
        with urlopen(request, timeout=3) as response:
            tags = json.loads(response.read().decode())
            if not tags:
                return None
            # Find the highest version tag
            versions = []
            for tag in tags:
                name = tag.get("name", "")
                # Strip 'v' prefix if present (e.g., "v0.2.1" -> "0.2.1")
                version_str = name.lstrip("v")
                try:
                    parsed = _parse_version(version_str)
                    if parsed:  # Only include valid versions
                        versions.append((parsed, version_str))
                except (ValueError, IndexError):
                    continue
            if not versions:
                return None
            # Return the highest version
            versions.sort(reverse=True, key=lambda x: x[0])
            return versions[0][1]
    except (URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None


def _read_cache() -> dict | None:
    """Read the version cache file."""
    if not VERSION_CACHE_FILE.exists():
        return None
    try:
        return json.loads(VERSION_CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(latest_version: str) -> None:
    """Write the version cache file."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "latest_version": latest_version,
            "checked_at": time.time(),
        }
        VERSION_CACHE_FILE.write_text(json.dumps(cache_data))
    except OSError:
        pass  # Silently ignore cache write failures


def get_latest_version() -> str | None:
    """Get the latest version, using cache if available and fresh."""
    cache = _read_cache()
    if cache:
        checked_at = cache.get("checked_at", 0)
        if time.time() - checked_at < CACHE_TTL_SECONDS:
            return cache.get("latest_version")

    latest = _fetch_latest_version()
    if latest:
        _write_cache(latest)
    return latest


def check_for_updates() -> None:
    """Check if a newer version is available and print a warning if so."""
    latest_version = get_latest_version()
    if not latest_version:
        return

    current = _parse_version(__version__)
    latest = _parse_version(latest_version)

    if latest > current:
        print_warning(
            f"A new version of wiggum is available: {latest_version} "
            f"(you have {__version__}). Run 'wiggum update' to upgrade."
        )
