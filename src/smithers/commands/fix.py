"""Fix command - iteratively fix PR review comments and CI failures."""

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer

from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.exceptions import DependencyMissingError, SmithersError
from smithers.models.config import Config, set_config
from smithers.prompts.fix import render_fix_planning_prompt, render_fix_prompt
from smithers.services.claude import ClaudeService
from smithers.services.git import GitService
from smithers.services.github import GitHubService
from smithers.services.tmux import TmuxService


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


def fix(
    design_doc: Annotated[
        Path,
        typer.Argument(
            help="Path to the design document markdown file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    pr_identifiers: Annotated[
        list[str],
        typer.Argument(help="PR numbers or GitHub PR URLs to process"),
    ],
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Claude model to use"),
    ] = "claude-opus-4-5-20251101",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without executing"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", help="Maximum fix iterations (0 = unlimited)"),
    ] = 0,
) -> None:
    """Fix review comments and CI failures on PRs.

    This command loops until all review comments are addressed and CI passes
    on all specified PRs.
    """
    if not pr_identifiers:
        print_error("At least one PR number or URL is required")
        raise typer.Exit(1)

    # Parse PR identifiers into numbers
    pr_numbers: list[int] = []
    for identifier in pr_identifiers:
        try:
            pr_numbers.append(parse_pr_identifier(identifier))
        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1) from e

    # Set up configuration
    config = Config(
        model=model,
        dry_run=dry_run,
        verbose=verbose,
    )
    set_config(config)

    # Initialize services
    git_service = GitService()
    tmux_service = TmuxService()
    claude_service = ClaudeService(model=model)
    github_service = GitHubService()

    # Check dependencies
    try:
        git_service.ensure_dependencies()
        tmux_service.ensure_dependencies()
        claude_service.ensure_dependencies()
        github_service.ensure_dependencies()
    except DependencyMissingError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    print_header("Smithers Loop: Fixing PR Comments (Parallel)")
    console.print(f"Design doc: [cyan]{design_doc}[/cyan]")
    console.print(f"PRs to process: [cyan]{', '.join(f'#{pr}' for pr in pr_numbers)}[/cyan]")
    console.print("Will keep looping until all comments are addressed")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        return

    # Get branch names for each PR
    print_info("\nFetching branch names for PRs...")
    pr_branches: dict[int, str] = {}
    for pr_num in pr_numbers:
        try:
            pr_info = github_service.get_pr_info(pr_num)
            pr_branches[pr_num] = pr_info.branch
            console.print(f"  PR #{pr_num}: {pr_info.branch}")
        except SmithersError as e:
            print_error(f"Failed to get info for PR #{pr_num}: {e}")
            raise typer.Exit(1) from e

    design_doc_base = design_doc.stem

    iteration = 0
    try:
        while True:
            iteration += 1

            if max_iterations > 0 and iteration > max_iterations:
                console.print(f"\n[yellow]Reached max iterations ({max_iterations})[/yellow]")
                break

            print_header(f"ITERATION {iteration}")

            # Create timestamped TODO file for this iteration in ~/.smithers/plans
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
            todo_file = config.plans_dir / f"{design_doc_base}.smithers-{timestamp}.md"

            result = _run_fix_iteration(
                design_doc=design_doc,
                todo_file=todo_file,
                pr_numbers=pr_numbers,
                pr_branches=pr_branches,
                git_service=git_service,
                tmux_service=tmux_service,
                claude_service=claude_service,
                config=config,
            )

            if result["all_done"]:
                print_header("ALL COMMENTS RESOLVED & CI PASSING!")
                console.print(f"Completed in {iteration} iteration(s)")
                break

            if result["comments_done_ci_failing"]:
                console.print("\n[yellow]Comments resolved but CI still failing[/yellow]")
                console.print("Continuing to fix CI issues...")
                time.sleep(10)
                continue

            console.print(f"\nIteration {iteration} complete")
            console.print("Checking for new comments in 10 seconds...")
            time.sleep(10)

    finally:
        # Cleanup on exit
        git_service.cleanup_all_worktrees()
        tmux_service.kill_all_smithers_sessions()

    print_header("Smithers Loop Complete!")
    console.print(f"Processed {len(pr_numbers)} PRs")
    console.print(f"Total iterations: {iteration}")


def _run_fix_iteration(
    design_doc: Path,
    todo_file: Path,
    pr_numbers: list[int],
    pr_branches: dict[int, str],
    git_service: GitService,
    tmux_service: TmuxService,
    claude_service: ClaudeService,
    config: Config,
) -> dict[str, bool | int]:
    """Run a single fix iteration.

    Returns:
        Dict with status flags and counts
    """
    design_content = design_doc.read_text()

    # Create fix planning prompt
    planning_prompt = render_fix_planning_prompt(
        design_doc_path=design_doc,
        design_content=design_content,
        pr_numbers=pr_numbers,
        todo_file_path=todo_file,
    )

    print_info("Running Claude Code to fetch PR comments and create fix plan...")
    result = claude_service.run_prompt(planning_prompt)

    if config.verbose:
        console.print(result.output)

    if not result.success:
        console.print("[yellow]Claude Code failed during TODO creation. Retrying...[/yellow]")
        time.sleep(5)
        return {"all_done": False, "comments_done_ci_failing": False}

    if not todo_file.exists():
        console.print(f"[yellow]TODO file not created at {todo_file}. Retrying...[/yellow]")
        time.sleep(5)
        return {"all_done": False, "comments_done_ci_failing": False}

    print_success(f"Review fix plan created: {todo_file}")
    todo_content = todo_file.read_text()

    # Process each PR in parallel
    print_info("\nCreating worktrees and launching Claude sessions for each PR...")

    group_data: list[dict[str, object]] = []

    for pr_num in pr_numbers:
        branch = pr_branches[pr_num]
        console.print(f"\nSetting up PR #{pr_num} (branch: {branch})...")

        try:
            worktree_path = git_service.create_worktree(branch, f"origin/{branch}")
        except SmithersError:
            console.print(f"[yellow]Trying alternative worktree creation for {branch}[/yellow]")
            try:
                worktree_path = git_service.create_worktree(branch, branch)
            except SmithersError as e:
                console.print(f"[red]Could not create worktree for PR #{pr_num}: {e}[/red]")
                continue

        # Create prompt file
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        prompt_file = config.temp_dir / f"smithers-fix-pr-{pr_num}-{timestamp}.prompt"
        output_file = prompt_file.with_suffix(".prompt.output")
        exit_file = prompt_file.with_suffix(".prompt.exit")

        # Generate fix prompt
        prompt = render_fix_prompt(
            pr_number=pr_num,
            branch=branch,
            worktree_path=worktree_path,
            design_doc_path=design_doc,
            design_content=design_content,
            todo_file_path=todo_file,
            todo_content=todo_content,
        )
        prompt_file.write_text(prompt)

        group_data.append(
            {
                "pr_number": pr_num,
                "branch": branch,
                "worktree_path": worktree_path,
                "prompt_file": prompt_file,
                "output_file": output_file,
                "exit_file": exit_file,
            }
        )

    # Launch all Claude sessions
    sessions: list[str] = []
    for data in group_data:
        command = claude_service.create_tmux_command(
            prompt_file=Path(str(data["prompt_file"])),
            output_file=Path(str(data["output_file"])),
            exit_file=Path(str(data["exit_file"])),
        )

        session = tmux_service.create_session(
            name=str(data["branch"]),
            workdir=Path(str(data["worktree_path"])),
            command=command,
        )
        sessions.append(session)
        console.print(f"  PR #{data['pr_number']}: tmux session '{session}'")

    # Wait for all sessions
    tmux_service.wait_for_sessions(sessions, poll_interval=config.poll_interval)

    # Collect results
    print_info("\nCollecting results from all PRs...")

    total_unresolved = 0
    total_addressed = 0
    all_done = True
    all_ci_passing = True
    combined_output = ""

    for data in group_data:
        pr_num = data["pr_number"]
        output_file = Path(str(data["output_file"]))
        prompt_file = Path(str(data["prompt_file"]))
        exit_file = Path(str(data["exit_file"]))
        branch = str(data["branch"])

        if output_file.exists():
            output = output_file.read_text()
            combined_output += output

            if config.verbose:
                print_header(f"OUTPUT FROM PR #{pr_num}")
                console.print(output)

            # Extract results from JSON (with fallback to legacy regex)
            from smithers.services.claude import ClaudeResult

            fix_result = ClaudeResult(output=output, exit_code=0, success=True)
            json_output = fix_result.extract_json()

            if json_output:
                # Use JSON output
                if not json_output.get("done", False):
                    all_done = False
                if json_output.get("ci_status") == "failing":
                    all_ci_passing = False
                total_unresolved += json_output.get("unresolved_before", 0)
                total_addressed += json_output.get("addressed", 0)
            else:
                # Fallback to legacy regex format
                if not re.search(rf"PR_{pr_num}_DONE:\s*true", output):
                    all_done = False
                if re.search(rf"PR_{pr_num}_CI_STATUS:\s*failing", output):
                    all_ci_passing = False

                unresolved_match = re.search(rf"PR_{pr_num}_UNRESOLVED_BEFORE:\s*(\d+)", output)
                addressed_match = re.search(rf"PR_{pr_num}_ADDRESSED:\s*(\d+)", output)

                if unresolved_match:
                    total_unresolved += int(unresolved_match.group(1))
                if addressed_match:
                    total_addressed += int(addressed_match.group(1))
        else:
            console.print(f"[yellow]Warning: No output file found for PR #{pr_num}[/yellow]")
            all_done = False

        # Cleanup temp files
        for f in [prompt_file, output_file, exit_file]:
            if f.exists():
                f.unlink()

        # Cleanup worktree
        git_service.cleanup_worktree(branch)

    # Print summary
    console.print(f"\nTotal unresolved before: {total_unresolved}")
    console.print(f"Total addressed: {total_addressed}")
    console.print(f"All CI passing: {all_ci_passing}")
    console.print(f"All done: {all_done}")

    return {
        "all_done": all_done and all_ci_passing,
        "comments_done_ci_failing": all_done and not all_ci_passing,
        "total_unresolved": total_unresolved,
        "total_addressed": total_addressed,
    }
