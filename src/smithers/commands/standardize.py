"""Standardize command - standardize titles and descriptions for a series of PRs."""

import subprocess
from typing import Annotated, Any
from urllib.parse import urlparse

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.exceptions import DependencyMissingError, GitHubError
from smithers.logging_config import get_logger, log_subprocess_result
from smithers.prompts.standardize import (
    render_standardize_analysis_prompt,
    render_standardize_update_prompt,
)
from smithers.services.claude import ClaudeService
from smithers.services.github import GitHubService

logger = get_logger("smithers.commands.standardize")


def parse_pr_identifier(identifier: str) -> int:
    """Parse a PR number from either a number string or a GitHub PR URL.

    Args:
        identifier: Either a PR number (e.g., "123") or a GitHub PR URL
                   (e.g., "https://github.com/owner/repo/pull/123")

    Returns:
        The PR number as an integer

    Raises:
        ValueError: If the identifier cannot be parsed as a PR number
    """
    # Try parsing as a simple integer first
    try:
        return int(identifier)
    except ValueError:
        pass

    # Try parsing as a GitHub PR URL
    parsed = urlparse(identifier)
    if parsed.netloc in ("github.com", "www.github.com"):
        # URL format: https://github.com/owner/repo/pull/123
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 4 and parts[2] == "pull":
            try:
                return int(parts[3])
            except ValueError:
                pass

    raise ValueError(
        f"Invalid PR identifier: {identifier}. "
        "Expected a PR number (e.g., 123) or GitHub URL (e.g., https://github.com/owner/repo/pull/123)"
    )


def fetch_pr_diff(pr_number: int) -> str:
    """Fetch the diff for a PR using gh pr diff.

    Args:
        pr_number: The PR number

    Returns:
        The diff as a string

    Raises:
        GitHubError: If fetching the diff fails
    """
    logger.info(f"Fetching diff for PR #{pr_number}")
    cmd = ["gh", "pr", "diff", str(pr_number)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            text=True,
        )
        log_subprocess_result(logger, cmd, result.returncode, result.stdout, result.stderr)
        return result.stdout
    except subprocess.CalledProcessError as e:
        log_subprocess_result(logger, cmd, e.returncode, e.stdout, e.stderr, success=False)
        logger.exception(f"Failed to fetch diff for PR #{pr_number}")
        raise GitHubError(f"Failed to fetch diff for PR #{pr_number}: {e.stderr}") from e


def standardize(
    pr_identifiers: Annotated[
        list[str],
        typer.Argument(help="PR numbers or GitHub PR URLs to standardize"),
    ],
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Claude model to use"),
    ] = "claude-opus-4-5-20251101",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show analysis without updating PRs"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Standardize titles and descriptions for a series of related PRs.

    Analyzes all PR diffs to understand the overall feature being implemented,
    then updates each PR with consistent titles in the format:
    "Feature Name (N/M): Description"

    Each PR description will include an overview, a table of all PRs in the
    series, and dependency information.
    """
    print_random_quote()

    logger.info("=" * 60)
    logger.info("Starting standardize command")
    logger.info(f"  pr_identifiers: {pr_identifiers}")
    logger.info(f"  model: {model}")
    logger.info(f"  dry_run: {dry_run}")
    logger.info(f"  verbose: {verbose}")
    logger.info("=" * 60)

    if not pr_identifiers:
        logger.error("No PR identifiers provided")
        print_error("At least one PR number or URL is required")
        raise typer.Exit(1)

    # Parse PR identifiers into numbers
    pr_numbers: list[int] = []
    for identifier in pr_identifiers:
        try:
            pr_numbers.append(parse_pr_identifier(identifier))
        except ValueError as e:
            logger.exception(f"Invalid PR identifier: {identifier}")
            print_error(str(e))
            raise typer.Exit(1) from e

    logger.info(f"Parsed PR numbers: {pr_numbers}")

    # Initialize services
    claude_service = ClaudeService(model=model)
    github_service = GitHubService()

    # Check dependencies
    logger.info("Checking dependencies")
    try:
        claude_service.ensure_dependencies()
        github_service.ensure_dependencies()
        logger.info("All dependencies satisfied")
    except DependencyMissingError as e:
        logger.exception("Missing dependencies")
        print_error(str(e))
        raise typer.Exit(1) from e

    print_header("Smithers: Standardizing PR Series")
    console.print(f"PRs to process: [cyan]{', '.join(f'#{pr}' for pr in pr_numbers)}[/cyan]")
    console.print(f"Model: [cyan]{model}[/cyan]")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - Will show analysis but not update PRs[/yellow]")

    # Fetch PR info and diffs
    print_info("\nFetching PR information and diffs...")

    pr_diffs: list[dict[str, str | int]] = []
    for pr_num in pr_numbers:
        try:
            pr_info = github_service.get_pr_info(pr_num)
            diff = fetch_pr_diff(pr_num)
            pr_diffs.append({
                "number": pr_num,
                "title": pr_info.title,
                "diff": diff,
            })
            console.print(f"  PR #{pr_num}: {pr_info.title}")
            logger.info(f"PR #{pr_num}: title={pr_info.title}, diff_length={len(diff)}")
        except GitHubError as e:
            logger.exception(f"Failed to get info for PR #{pr_num}")
            print_error(f"Failed to get info for PR #{pr_num}: {e}")
            raise typer.Exit(1) from e

    # Stage 1: Run analysis prompt
    print_header("Stage 1: Analyzing PR Series")
    print_info("Running Claude to analyze all PRs and determine standardized structure...")

    analysis_prompt = render_standardize_analysis_prompt(pr_diffs)
    logger.debug(f"Analysis prompt length: {len(analysis_prompt)} chars")

    analysis_result = claude_service.run_prompt(analysis_prompt)

    if verbose:
        print_header("Analysis Output")
        console.print(analysis_result.output)

    if not analysis_result.success:
        logger.error(f"Claude analysis failed: exit_code={analysis_result.exit_code}")
        print_error("Claude analysis failed. Please try again.")
        raise typer.Exit(1)

    # Extract JSON output from analysis
    analysis_json = analysis_result.extract_json()
    if not analysis_json:
        logger.error("Failed to extract JSON from analysis output")
        print_error("Failed to extract structured output from analysis. Please try again.")
        raise typer.Exit(1)

    if analysis_json.get("error"):
        logger.error(f"Analysis returned error: {analysis_json['error']}")
        print_error(f"Analysis error: {analysis_json['error']}")
        raise typer.Exit(1)

    # Display analysis results
    _display_analysis_results(analysis_json)

    # If dry run, stop here
    if dry_run:
        print_header("Dry Run Complete")
        console.print("Analysis complete. Run without --dry-run to apply changes.")
        return

    # Stage 2: Run update prompt
    print_header("Stage 2: Updating PRs")
    print_info("Running Claude to update PR titles and descriptions...")

    feature_name = analysis_json.get("feature_name", "Unknown Feature")
    total_prs = analysis_json.get("total_prs", len(pr_numbers))
    prs_data = analysis_json.get("prs", [])

    update_prompt = render_standardize_update_prompt(
        feature_name=feature_name,
        total_prs=total_prs,
        prs=prs_data,
    )
    logger.debug(f"Update prompt length: {len(update_prompt)} chars")

    update_result = claude_service.run_prompt(update_prompt)

    if verbose:
        print_header("Update Output")
        console.print(update_result.output)

    if not update_result.success:
        logger.error(f"Claude update failed: exit_code={update_result.exit_code}")
        print_error("Claude update failed. Some PRs may have been partially updated.")
        raise typer.Exit(1)

    # Extract JSON output from update
    update_json = update_result.extract_json()
    if not update_json:
        logger.error("Failed to extract JSON from update output")
        print_error("Failed to extract structured output from update.")
        raise typer.Exit(1)

    if update_json.get("error"):
        logger.error(f"Update returned error: {update_json['error']}")
        print_error(f"Update error: {update_json['error']}")
        raise typer.Exit(1)

    # Display update results
    _display_update_results(update_json)

    print_header("Standardization Complete!")
    console.print(f"Successfully standardized {len(pr_numbers)} PRs")


def _display_analysis_results(analysis: dict[str, Any]) -> None:
    """Display the analysis results in a formatted way."""
    print_header("Analysis Results")

    feature_name = analysis.get("feature_name", "Unknown")
    total_prs = analysis.get("total_prs", 0)
    prs = analysis.get("prs", [])

    console.print(f"[bold]Feature Name:[/bold] {feature_name}")
    console.print(f"[bold]Total PRs:[/bold] {total_prs}")
    console.print()

    for pr in prs:
        pr_num = pr.get("number", "?")
        position = pr.get("position", "?")
        title = pr.get("suggested_title", "No title")
        summary = pr.get("summary", "No summary")

        console.print(f"[cyan]PR #{pr_num}[/cyan] (Position {position}/{total_prs})")
        console.print(f"  [bold]Title:[/bold] {title}")
        console.print(f"  [bold]Summary:[/bold] {summary}")

        key_changes = pr.get("key_changes", [])
        if key_changes:
            console.print("  [bold]Key Changes:[/bold]")
            for change in key_changes:
                console.print(f"    - {change}")
        console.print()


def _display_update_results(update: dict[str, Any]) -> None:
    """Display the update results in a formatted way."""
    updated_prs = update.get("updated_prs", [])

    success_count = 0
    for pr in updated_prs:
        pr_num = pr.get("number", "?")
        new_title = pr.get("new_title", "Unknown")
        success = pr.get("success", False)

        if success:
            print_success(f'PR #{pr_num}: Updated to "{new_title}"')
            success_count += 1
        else:
            print_error(f"PR #{pr_num}: Failed to update")

    console.print()
    console.print(f"Updated {success_count}/{len(updated_prs)} PRs successfully")
