"""Fix command - iteratively fix PR review comments and CI failures."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import (
    console,
    print_error,
    print_header,
    print_info,
    print_success,
)
from smithers.exceptions import DependencyMissingError, SmithersError
from smithers.logging_config import get_logger, get_session_log_file
from smithers.models.config import Config, set_config
from smithers.prompts.fix import render_fix_planning_prompt, render_fix_prompt
from smithers.services.claude import ClaudeResult, ClaudeService
from smithers.services.git import GitService
from smithers.services.github import GitHubService
from smithers.services.tmux import TmuxService
from smithers.services.vibekanban import (
    VibekanbanService,
    create_vibekanban_service,
    get_vibekanban_url,
)
from smithers.utils.parsing import parse_pr_identifier

logger = get_logger("smithers.commands.fix")


# Type alias for PR data used in fix iterations
PRData = dict[str, object]


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
    original_todo: Annotated[
        Path | None,
        typer.Option(
            "--todo",
            "-t",
            help="Original implementation TODO file (from implement phase)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Claude model to use"),
    ] = "claude-opus-4-5-20251101",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", "-n", help="Show what would be done without executing"
        ),
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
    print_random_quote()

    logger.info("=" * 60)
    logger.info("Starting fix command")
    logger.info(f"  design_doc: {design_doc}")
    logger.info(f"  pr_identifiers: {pr_identifiers}")
    logger.info(f"  original_todo: {original_todo}")
    logger.info(f"  model: {model}")
    logger.info(f"  dry_run: {dry_run}")
    logger.info(f"  verbose: {verbose}")
    logger.info(f"  max_iterations: {max_iterations}")
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

    # Set up configuration
    config = Config(
        branch_prefix="",  # Not used by fix command (works on existing PRs)
        dry_run=dry_run,
        verbose=verbose,
    )
    set_config(config)

    # Initialize services
    git_service = GitService()
    tmux_service = TmuxService()
    claude_service = ClaudeService(model=model)
    github_service = GitHubService()
    vibekanban_service = create_vibekanban_service()

    # Check dependencies
    logger.info("Checking dependencies")
    try:
        tmux_service.ensure_rejoinable_session(
            session_name=f"smithers-fix-{design_doc.stem}",
            argv=sys.argv,
        )
        git_service.ensure_dependencies()
        tmux_service.ensure_dependencies()
        claude_service.ensure_dependencies()
        github_service.ensure_dependencies()
        logger.info("All dependencies satisfied")
    except DependencyMissingError as e:
        logger.exception("Missing dependencies")
        print_error(str(e))
        raise typer.Exit(1) from e

    print_header("Smithers Loop: Fixing PR Comments (Parallel)")
    console.print(f"Design doc: [cyan]{design_doc}[/cyan]")
    if original_todo:
        console.print(f"Original TODO: [cyan]{original_todo}[/cyan]")
    console.print(
        f"PRs to process: [cyan]{', '.join(f'#{pr}' for pr in pr_numbers)}[/cyan]"
    )
    vibekanban_url = get_vibekanban_url()
    if vibekanban_url:
        console.print(f"Vibekanban: [cyan]{vibekanban_url}[/cyan]")

    # Print log and output locations
    console.print(f"Log file: [cyan]{get_session_log_file()}[/cyan]")
    console.print(f"Claude output dir: [cyan]{config.temp_dir}[/cyan]")

    console.print("Will keep looping until all comments are addressed")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        return

    # Get branch names and URLs for each PR
    logger.info("Fetching branch names for PRs")
    print_info("\nFetching branch names for PRs...")
    pr_branches: dict[int, str] = {}
    pr_urls: dict[int, str] = {}
    for pr_num in pr_numbers:
        try:
            pr_info = github_service.get_pr_info(pr_num)
            pr_branches[pr_num] = pr_info.branch
            pr_urls[pr_num] = pr_info.url
            logger.info(f"PR #{pr_num}: branch={pr_info.branch}, url={pr_info.url}")
            console.print(f"  PR #{pr_num}: {pr_info.branch}")
        except SmithersError as e:
            logger.exception(f"Failed to get info for PR #{pr_num}")
            print_error(f"Failed to get info for PR #{pr_num}: {e}")
            raise typer.Exit(1) from e

    design_doc_base = design_doc.stem

    iteration = 0
    exit_error: Exception | None = None
    try:
        while True:
            iteration += 1
            logger.info(f"Starting iteration {iteration}")

            if max_iterations > 0 and iteration > max_iterations:
                logger.info(f"Reached max iterations ({max_iterations})")
                console.print(
                    f"\n[yellow]Reached max iterations ({max_iterations})[/yellow]"
                )
                break

            print_header(f"ITERATION {iteration}")

            # Create timestamped TODO file for this iteration in ~/.smithers/plans
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
            todo_file = config.plans_dir / f"{design_doc_base}.smithers-{timestamp}.md"

            result = _run_fix_iteration(
                design_doc=design_doc,
                original_todo=original_todo,
                todo_file=todo_file,
                pr_numbers=pr_numbers,
                pr_branches=pr_branches,
                pr_urls=pr_urls,
                git_service=git_service,
                tmux_service=tmux_service,
                claude_service=claude_service,
                vibekanban_service=vibekanban_service,
                config=config,
            )

            logger.info(f"Iteration {iteration} result: {result}")

            if result["all_done"]:
                logger.info(f"All done! Completed in {iteration} iteration(s)")
                print_header("ALL COMMENTS RESOLVED & CI PASSING!")
                console.print(f"Completed in {iteration} iteration(s)")
                break

            if result["comments_done_ci_failing"]:
                logger.info("Comments resolved but CI still failing")
                console.print(
                    "\n[yellow]Comments resolved but CI still failing[/yellow]"
                )
                console.print("Continuing to fix CI issues...")
                continue

            logger.info(f"Iteration {iteration} complete, starting next check")
            console.print(f"\nIteration {iteration} complete")

    except KeyboardInterrupt:
        logger.warning("Fix loop interrupted by user")
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        exit_error = e
        logger.exception("Unexpected error in fix loop")
        console.print(f"\n[red]Unexpected error: {e}[/red]")
    finally:
        # Cleanup on exit
        logger.info("Cleanup: removing worktrees and killing sessions")
        git_service.cleanup_all_worktrees()
        tmux_service.kill_all_smithers_sessions()

    if exit_error:
        raise typer.Exit(1) from exit_error

    # Mark all vibekanban fix tasks as completed (safety net)
    vibekanban_service.mark_fix_tasks_completed(pr_numbers, pr_branches)

    print_header("Smithers Loop Complete!")
    console.print(f"Processed {len(pr_numbers)} PRs")
    console.print(f"Total iterations: {iteration}")


def _run_fix_planning(
    design_doc: Path,
    design_content: str,
    original_todo_content: str | None,
    pr_numbers: list[int],
    todo_file: Path,
    claude_service: ClaudeService,
    config: Config,
) -> tuple[bool, str, int, int, int]:
    """Run the planning phase of a fix iteration.

    Args:
        design_doc: Path to the design document.
        design_content: Content of the design document.
        original_todo_content: Content of the original implementation TODO (from implement phase).
        pr_numbers: List of PR numbers to fix.
        todo_file: Path to the TODO file for this iteration.
        claude_service: Claude service instance.
        config: Configuration instance.

    Returns:
        Tuple of (success, todo_content, num_incomplete_items, num_comments, num_ci_failures).
        If success is False, todo_content will be empty.
    """
    planning_prompt = render_fix_planning_prompt(
        design_doc_path=design_doc,
        design_content=design_content,
        original_todo_content=original_todo_content,
        pr_numbers=pr_numbers,
        todo_file_path=todo_file,
    )

    logger.info("Running Claude Code to create fix plan")
    print_info("Running Claude Code to fetch PR comments and create fix plan...")
    result = claude_service.run_prompt(planning_prompt)

    if config.verbose:
        console.print(result.output)

    if not result.success:
        logger.warning(
            f"Claude Code failed during TODO creation: exit_code={result.exit_code}"
        )
        console.print(
            "[yellow]Claude Code failed during TODO creation. Retrying...[/yellow]"
        )
        return (False, "", 0, 0, 0)

    if not todo_file.exists():
        logger.warning(f"TODO file not created at {todo_file}")
        console.print(
            f"[yellow]TODO file not created at {todo_file}. Retrying...[/yellow]"
        )
        return (False, "", 0, 0, 0)

    logger.info(f"Fix plan created: {todo_file}")
    print_success(f"Review fix plan created: {todo_file}")
    todo_content = todo_file.read_text()

    planning_json = result.extract_json()
    num_incomplete_items = (
        planning_json.get("num_incomplete_items", 0) if planning_json else 0
    )
    num_comments = planning_json.get("num_comments", 0) if planning_json else 0
    num_ci_failures = planning_json.get("num_ci_failures", 0) if planning_json else 0
    logger.info(
        f"Planning found: {num_incomplete_items} incomplete items, "
        f"{num_comments} comments, {num_ci_failures} CI failures"
    )
    console.print(
        f"Found: [cyan]{num_incomplete_items}[/cyan] incomplete items, "
        f"[cyan]{num_comments}[/cyan] unresolved comments, "
        f"[cyan]{num_ci_failures}[/cyan] CI failures"
    )

    return (True, todo_content, num_incomplete_items, num_comments, num_ci_failures)


def _setup_pr_worktrees(
    pr_numbers: list[int],
    pr_branches: dict[int, str],
    pr_urls: dict[int, str],
    design_doc: Path,
    design_content: str,
    original_todo_content: str | None,
    todo_file: Path,
    todo_content: str,
    num_incomplete_items: int,
    num_comments: int,
    num_ci_failures: int,
    git_service: GitService,
    vibekanban_service: VibekanbanService,
    config: Config,
) -> list[PRData]:
    """Set up worktrees and prepare data for each PR.

    Args:
        pr_numbers: List of PR numbers to fix.
        pr_branches: Mapping of PR numbers to branch names.
        pr_urls: Mapping of PR numbers to GitHub URLs.
        design_doc: Path to the design document.
        design_content: Content of the design document.
        original_todo_content: Content of the original implementation TODO (from implement phase).
        todo_file: Path to the TODO file for this iteration.
        todo_content: Content of the TODO file.
        num_incomplete_items: Number of incomplete implementation items found.
        num_comments: Number of unresolved comments found.
        num_ci_failures: Number of CI failures found.
        git_service: Git service instance.
        vibekanban_service: Vibekanban service for task tracking.
        config: Configuration instance.

    Returns:
        List of PR data dictionaries containing worktree paths, file paths, and task IDs.
    """
    print_info("\nCreating worktrees and launching Claude sessions for each PR...")
    group_data: list[PRData] = []

    for pr_num in pr_numbers:
        branch = pr_branches[pr_num]
        console.print(f"\nSetting up PR #{pr_num} (branch: {branch})...")

        try:
            worktree_path = git_service.create_worktree(branch, f"origin/{branch}")
        except SmithersError:
            console.print(
                f"[yellow]Trying alternative worktree creation for {branch}[/yellow]"
            )
            try:
                worktree_path = git_service.create_worktree(branch, branch)
            except SmithersError as e:
                console.print(
                    f"[red]Could not create worktree for PR #{pr_num}: {e}[/red]"
                )
                continue

        # Create prompt file and output files
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        prompt_file = config.temp_dir / f"smithers-fix-pr-{pr_num}-{timestamp}.prompt"
        output_file = prompt_file.with_suffix(".prompt.output")
        exit_file = prompt_file.with_suffix(".prompt.exit")
        stream_log_file = prompt_file.with_suffix(".prompt.stream.log")

        # Generate fix prompt
        prompt = render_fix_prompt(
            pr_number=pr_num,
            branch=branch,
            worktree_path=worktree_path,
            design_doc_path=design_doc,
            design_content=design_content,
            original_todo_content=original_todo_content,
            todo_file_path=todo_file,
            todo_content=todo_content,
        )
        prompt_file.write_text(prompt)

        # Find or create vibekanban task for this PR fix session
        pr_vk_task_id = _get_or_create_vibekanban_task(
            pr_num=pr_num,
            branch=branch,
            pr_url=pr_urls.get(pr_num, ""),
            num_incomplete_items=num_incomplete_items,
            num_comments=num_comments,
            num_ci_failures=num_ci_failures,
            vibekanban_service=vibekanban_service,
        )

        group_data.append(
            {
                "pr_number": pr_num,
                "branch": branch,
                "worktree_path": worktree_path,
                "prompt_file": prompt_file,
                "output_file": output_file,
                "exit_file": exit_file,
                "stream_log_file": stream_log_file,
                "vk_task_id": pr_vk_task_id,
            }
        )

    return group_data


def _get_or_create_vibekanban_task(
    pr_num: int,
    branch: str,
    pr_url: str,
    num_incomplete_items: int,
    num_comments: int,
    num_ci_failures: int,
    vibekanban_service: VibekanbanService,
) -> str | None:
    """Get or create a vibekanban task for a PR fix session.

    Args:
        pr_num: PR number.
        branch: Branch name.
        pr_url: GitHub PR URL.
        num_incomplete_items: Number of incomplete implementation items.
        num_comments: Number of unresolved comments.
        num_ci_failures: Number of CI failures.
        vibekanban_service: Vibekanban service instance.

    Returns:
        Task ID if found or created, None otherwise.
    """
    task_title = f"[fix] PR #{pr_num}: {branch}"
    task_description = (
        f"Fixing review comments on {branch}\n\nPR: {pr_url}"
        if pr_url
        else f"Fixing review comments on {branch}"
    )

    if num_incomplete_items > 0 or num_comments > 0 or num_ci_failures > 0:
        # Issues to fix - find or create task and set to in_progress
        pr_vk_task_id = vibekanban_service.find_or_create_task(
            title=task_title,
            description=task_description,
        )
        if pr_vk_task_id:
            logger.info(f"Using vibekanban task for PR #{pr_num}: {pr_vk_task_id}")
        return pr_vk_task_id
    # No issues - just find existing task (don't create) so we can mark it done
    existing_task = vibekanban_service.find_task(task_title)
    if existing_task:
        pr_vk_task_id = existing_task.get("id")
        if pr_vk_task_id:
            logger.info(
                f"Found existing vibekanban task for PR #{pr_num}: {pr_vk_task_id}"
            )
        return pr_vk_task_id
    logger.info(f"No vibekanban task for PR #{pr_num}: no issues to fix")
    return None


def _collect_fix_results(
    group_data: list[PRData],
    claude_service: ClaudeService,
    git_service: GitService,
    config: Config,
) -> dict[str, bool | int]:
    """Collect and process results from all PR fix sessions.

    Args:
        group_data: List of PR data dictionaries.
        claude_service: Claude service instance.
        git_service: Git service instance.
        config: Configuration instance.

    Returns:
        Dict with aggregated status flags and counts.
    """
    logger.info("Collecting results from all PRs")
    print_info("\nCollecting results from all PRs...")

    total_unresolved = 0
    total_addressed = 0
    all_done = True
    all_ci_passing = True
    all_base_merged = True
    all_merge_conflicts_resolved = True

    for data in group_data:
        pr_num = data["pr_number"]
        output_file = Path(str(data["output_file"]))
        prompt_file = Path(str(data["prompt_file"]))
        exit_file = Path(str(data["exit_file"]))
        stream_log_file = Path(str(data["stream_log_file"]))
        branch = str(data["branch"])

        result = _process_pr_result(
            pr_num=pr_num,
            output_file=output_file,
            claude_service=claude_service,
            config=config,
        )

        if not result["done"]:
            all_done = False
        if result["ci_failing"]:
            all_ci_passing = False
        if not result["base_merged"]:
            all_base_merged = False
        if not result["merge_conflicts_resolved"]:
            all_merge_conflicts_resolved = False
        total_unresolved += result["unresolved"]
        total_addressed += result["addressed"]

        # Cleanup temp files (keep stream log for debugging if verbose)
        _cleanup_pr_files(prompt_file, output_file, exit_file, stream_log_file, config)

        # Cleanup worktree
        git_service.cleanup_worktree(branch)

    # Print summary
    logger.info(
        f"Iteration summary: unresolved={total_unresolved}, addressed={total_addressed}, "
        f"ci_passing={all_ci_passing}, base_merged={all_base_merged}, "
        f"merge_conflicts_resolved={all_merge_conflicts_resolved}, all_done={all_done}"
    )
    console.print(f"\nTotal unresolved before: {total_unresolved}")
    console.print(f"Total addressed: {total_addressed}")
    console.print(f"All CI passing: {all_ci_passing}")
    console.print(f"All base branches merged: {all_base_merged}")
    console.print(f"All merge conflicts resolved: {all_merge_conflicts_resolved}")
    console.print(f"All done: {all_done}")

    return {
        "all_done": all_done,
        "all_ci_passing": all_ci_passing,
        "all_base_merged": all_base_merged,
        "all_merge_conflicts_resolved": all_merge_conflicts_resolved,
        "total_unresolved": total_unresolved,
        "total_addressed": total_addressed,
    }


def _process_pr_result(
    pr_num: object,
    output_file: Path,
    claude_service: ClaudeService,
    config: Config,
) -> dict[str, bool | int]:
    """Process the result from a single PR fix session.

    Args:
        pr_num: PR number.
        output_file: Path to the output file.
        claude_service: Claude service instance.
        config: Configuration instance.

    Returns:
        Dict with status flags for this PR.
    """
    result: dict[str, bool | int] = {
        "done": False,
        "ci_failing": False,
        "base_merged": True,
        "merge_conflicts_resolved": True,
        "unresolved": 0,
        "addressed": 0,
    }

    if not output_file.exists():
        logger.warning(f"No output file found for PR #{pr_num}: {output_file}")
        console.print(
            f"[yellow]Warning: No output file found for PR #{pr_num}[/yellow]"
        )
        return result

    raw_output = output_file.read_text()
    output = claude_service.parse_stream_json_output(raw_output)
    logger.debug(f"PR #{pr_num} output ({len(output)} chars)")

    # Log stream stats for debugging
    stats = claude_service.get_stream_stats(raw_output)
    if stats:
        logger.info(
            f"PR #{pr_num} stats: duration={stats.get('duration_ms')}ms, "
            f"cost=${stats.get('total_cost_usd', 0):.4f}"
        )

    if config.verbose:
        print_header(f"OUTPUT FROM PR #{pr_num}")
        console.print(output)

    fix_result = ClaudeResult(output=output, exit_code=0, success=True)
    json_output = fix_result.extract_json()

    if json_output:
        logger.debug(f"PR #{pr_num} JSON output: {json_output}")
        result["done"] = json_output.get("done", False)
        result["ci_failing"] = json_output.get("ci_status") == "failing"
        result["base_merged"] = json_output.get("base_branch_merged", False)
        result["merge_conflicts_resolved"] = (
            json_output.get("merge_conflicts") != "unresolved"
        )
        result["unresolved"] = json_output.get("unresolved_before", 0)
        result["addressed"] = json_output.get("addressed", 0)
    else:
        logger.warning(f"PR #{pr_num}: No JSON output found, assuming not done")

    return result


def _cleanup_pr_files(
    prompt_file: Path,
    output_file: Path,
    exit_file: Path,
    stream_log_file: Path,
    config: Config,
) -> None:
    """Clean up temporary files from a PR fix session.

    Args:
        prompt_file: Path to the prompt file.
        output_file: Path to the output file.
        exit_file: Path to the exit file.
        stream_log_file: Path to the stream log file.
        config: Configuration instance.
    """
    files_to_clean = [prompt_file, output_file, exit_file]
    if not config.verbose:
        files_to_clean.append(stream_log_file)
    for f in files_to_clean:
        if f.exists():
            f.unlink()
    if config.verbose and stream_log_file.exists():
        logger.info(f"Stream log preserved at: {stream_log_file}")


def _run_fix_iteration(
    design_doc: Path,
    original_todo: Path | None,
    todo_file: Path,
    pr_numbers: list[int],
    pr_branches: dict[int, str],
    pr_urls: dict[int, str],
    git_service: GitService,
    tmux_service: TmuxService,
    claude_service: ClaudeService,
    vibekanban_service: VibekanbanService,
    config: Config,
) -> dict[str, bool | int]:
    """Run a single fix iteration.

    Args:
        design_doc: Path to the design document.
        original_todo: Path to the original implementation TODO file (from implement phase).
        todo_file: Path to the TODO file for this iteration.
        pr_numbers: List of PR numbers to fix.
        pr_branches: Mapping of PR numbers to branch names.
        pr_urls: Mapping of PR numbers to GitHub URLs.
        git_service: Git service instance.
        tmux_service: Tmux service instance.
        claude_service: Claude service instance.
        vibekanban_service: Vibekanban service for task tracking.
        config: Configuration instance.

    Returns:
        Dict with status flags and counts
    """
    logger.info(
        f"Running fix iteration: pr_numbers={pr_numbers}, todo_file={todo_file}"
    )
    design_content = design_doc.read_text()
    original_todo_content = original_todo.read_text() if original_todo else None

    # Phase 1: Run planning to create fix TODO
    success, todo_content, num_incomplete_items, num_comments, num_ci_failures = (
        _run_fix_planning(
            design_doc=design_doc,
            design_content=design_content,
            original_todo_content=original_todo_content,
            pr_numbers=pr_numbers,
            todo_file=todo_file,
            claude_service=claude_service,
            config=config,
        )
    )

    if not success:
        return {"all_done": False, "comments_done_ci_failing": False}

    # Early exit: if there's nothing to fix, we're done
    if num_incomplete_items == 0 and num_comments == 0 and num_ci_failures == 0:
        logger.info("No incomplete items, comments, or CI failures found - all done!")
        print_success("Nothing to fix - all items complete, no comments, CI passing!")
        return {"all_done": True, "comments_done_ci_failing": False}

    # Phase 2: Set up worktrees and prepare data for each PR
    group_data = _setup_pr_worktrees(
        pr_numbers=pr_numbers,
        pr_branches=pr_branches,
        pr_urls=pr_urls,
        design_doc=design_doc,
        design_content=design_content,
        original_todo_content=original_todo_content,
        todo_file=todo_file,
        todo_content=todo_content,
        num_incomplete_items=num_incomplete_items,
        num_comments=num_comments,
        num_ci_failures=num_ci_failures,
        git_service=git_service,
        vibekanban_service=vibekanban_service,
        config=config,
    )

    # Phase 3: Launch all Claude sessions
    sessions: list[str] = []
    session_to_data: dict[str, PRData] = {}
    for data in group_data:
        command = claude_service.create_tmux_command(
            prompt_file=Path(str(data["prompt_file"])),
            output_file=Path(str(data["output_file"])),
            exit_file=Path(str(data["exit_file"])),
            stream_log_file=Path(str(data["stream_log_file"])),
        )

        session = tmux_service.create_session(
            name=str(data["branch"]),
            workdir=Path(str(data["worktree_path"])),
            command=command,
        )
        sessions.append(session)
        session_to_data[session] = data
        console.print(f"  PR #{data['pr_number']}: tmux session '{session}'")

    # Create callback for immediate vibekanban updates when each session completes
    def on_session_complete(session_name: str) -> None:
        """Update vibekanban status immediately when a session completes."""
        data = session_to_data.get(session_name)
        if not data:
            return

        vk_task_id = data.get("vk_task_id")
        if not vk_task_id:
            return

        output_file = Path(str(data["output_file"]))
        pr_num = data["pr_number"]
        pr_done = False

        if output_file.exists():
            raw_output = output_file.read_text()
            output = claude_service.parse_stream_json_output(raw_output)
            fix_result = ClaudeResult(output=output, exit_code=0, success=True)
            json_output = fix_result.extract_json()
            if json_output:
                pr_done = json_output.get("done", False)

        status = "completed" if pr_done else "failed"
        vibekanban_service.update_task_status(str(vk_task_id), status)
        logger.info(f"PR #{pr_num}: vibekanban status updated to {status}")

    # Wait for all sessions, updating vibekanban as each completes
    tmux_service.wait_for_sessions(
        sessions,
        poll_interval=config.poll_interval,
        on_session_complete=on_session_complete,
    )

    # Phase 4: Collect results
    results = _collect_fix_results(
        group_data=group_data,
        claude_service=claude_service,
        git_service=git_service,
        config=config,
    )

    # All conditions must be met for fix to be complete
    truly_all_done = (
        results["all_done"]
        and results["all_ci_passing"]
        and results["all_base_merged"]
        and results["all_merge_conflicts_resolved"]
        and results["total_unresolved"] == 0
    )

    return {
        "all_done": truly_all_done,
        "comments_done_ci_failing": results["all_done"]
        and not results["all_ci_passing"],
        "total_unresolved": results["total_unresolved"],
        "total_addressed": results["total_addressed"],
        "all_base_merged": results["all_base_merged"],
        "all_merge_conflicts_resolved": results["all_merge_conflicts_resolved"],
    }
