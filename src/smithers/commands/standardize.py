"""Standardize command - standardize titles and descriptions for a series of PRs."""

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any

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
from smithers.services.vibekanban import create_vibekanban_service, get_vibekanban_url
from smithers.utils.parsing import parse_pr_identifier

logger = get_logger("smithers.commands.standardize")


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
    vibekanban_service = create_vibekanban_service()

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
    vibekanban_url = get_vibekanban_url()
    if vibekanban_url:
        console.print(f"Vibekanban: [cyan]{vibekanban_url}[/cyan]")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - Will show analysis but not update PRs[/yellow]")

    # Create vibekanban task for tracking (only if not dry run)
    vk_task_id: str | None = None
    if not dry_run:
        pr_list = ", ".join(f"#{pr}" for pr in pr_numbers)
        # Create vibekanban task (created as in_progress by default)
        vk_task_id = vibekanban_service.create_task(
            title=f"Standardize PRs: {pr_list}",
            description=f"Standardizing titles and descriptions for: {pr_list}",
        )
        if vk_task_id:
            logger.info(f"Created vibekanban task: {vk_task_id}")

    # Fetch PR info and diffs, write diffs to temp files
    print_info("\nFetching PR information and diffs...")

    # Create a temp directory for diff files
    temp_dir = Path(tempfile.mkdtemp(prefix="smithers-standardize-"))
    logger.info(f"Created temp directory for diffs: {temp_dir}")

    pr_diffs: list[dict[str, str | int | Path]] = []
    for pr_num in pr_numbers:
        try:
            pr_info = github_service.get_pr_info(pr_num)
            diff = fetch_pr_diff(pr_num)

            # Write diff to a temp file
            diff_file = temp_dir / f"pr-{pr_num}.diff"
            diff_file.write_text(diff, encoding="utf-8")
            diff_length = len(diff)

            pr_diffs.append(
                {
                    "number": pr_num,
                    "title": pr_info.title,
                    "diff_file": diff_file,
                    "diff_length": diff_length,
                }
            )
            console.print(f"  PR #{pr_num}: {pr_info.title} ({diff_length:,} chars)")
            logger.info(
                f"PR #{pr_num}: title={pr_info.title}, diff_length={diff_length}, "
                f"diff_file={diff_file}"
            )
        except GitHubError as e:
            logger.exception(f"Failed to get info for PR #{pr_num}")
            print_error(f"Failed to get info for PR #{pr_num}: {e}")
            raise typer.Exit(1) from e

    # Stage 1: Run analysis prompt
    print_header("Stage 1: Analyzing PR Series")
    print_info("Running Claude to analyze all PRs and determine standardized structure...")
    print_info("(Using auto-compact for large diffs)")

    analysis_prompt = render_standardize_analysis_prompt(pr_diffs)
    logger.debug(f"Analysis prompt length: {len(analysis_prompt)} chars")

    # Run with auto_compact enabled to handle large diffs
    analysis_result = claude_service.run_prompt(analysis_prompt, auto_compact=True)

    if verbose:
        print_header("Analysis Output")
        console.print(analysis_result.output)

    if not analysis_result.success:
        logger.error(f"Claude analysis failed: exit_code={analysis_result.exit_code}")
        logger.error(f"Claude output: {analysis_result.output}")
        # Extract and show the actual error message
        error_msg = analysis_result.output.strip()
        if error_msg:
            print_error(f"Claude analysis failed: {error_msg}")
        else:
            print_error(f"Claude analysis failed with exit code {analysis_result.exit_code}")
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

    update_result = claude_service.run_prompt(update_prompt, auto_compact=True)

    if verbose:
        print_header("Update Output")
        console.print(update_result.output)

    if not update_result.success:
        logger.error(f"Claude update failed: exit_code={update_result.exit_code}")
        logger.error(f"Claude output: {update_result.output}")
        # Extract and show the actual error message
        error_msg = update_result.output.strip()
        if error_msg:
            print_error(f"Claude update failed: {error_msg}")
        else:
            print_error(
                f"Claude update failed with exit code {update_result.exit_code}. "
                "Some PRs may have been partially updated."
            )
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

    # Update vibekanban task status
    if vk_task_id:
        vibekanban_service.update_task_status(vk_task_id, "completed")


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
