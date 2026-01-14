"""Implement command - creates staged PRs from a design document."""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, TypedDict

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.exceptions import DependencyMissingError, SmithersError
from smithers.logging_config import get_logger
from smithers.models.config import Config, set_config
from smithers.models.todo import TodoFile
from smithers.prompts.implementation import render_implementation_prompt
from smithers.prompts.planning import render_planning_prompt
from smithers.services.claude import ClaudeService
from smithers.services.git import GitService
from smithers.services.tmux import TmuxService
from smithers.services.todo_updater import TodoUpdater

logger = get_logger("smithers.commands.implement")

if TYPE_CHECKING:
    from smithers.models.stage import Stage


class StageData(TypedDict):
    """Type definition for stage data dictionary."""

    stage: Stage
    worktree_path: Path
    prompt_file: Path
    output_file: Path
    exit_file: Path


@dataclass
class PlanResult:
    """Result of generating a plan."""

    todo_file: Path
    num_stages: int
    design_content: str


def run_planning_session(
    *,
    design_doc: Path,
    todo_file: Path,
    claude_service: ClaudeService,
    config: Config,
) -> PlanResult:
    """Generate a TODO plan via Claude Code."""
    logger.info(f"Starting planning session: design_doc={design_doc}, todo_file={todo_file}")
    design_content = design_doc.read_text()
    logger.debug(f"Design doc size: {len(design_content)} chars")

    planning_prompt = render_planning_prompt(
        design_doc_path=design_doc,
        design_content=design_content,
        todo_file_path=todo_file,
        branch_prefix=config.branch_prefix,
    )

    print_info("Running Claude Code for planning...")
    result = claude_service.run_prompt(planning_prompt)

    if config.verbose:
        console.print(result.output)

    if not result.success:
        logger.error(f"Claude Code failed during planning: exit_code={result.exit_code}")
        raise SmithersError(f"Claude Code failed during planning: {result.output}")

    if not todo_file.exists():
        logger.error(f"TODO file was not created at {todo_file}")
        raise SmithersError(f"TODO file was not created at {todo_file}")

    json_output = result.extract_json()
    num_stages = json_output.get("num_stages") if json_output else result.extract_int("NUM_STAGES")

    if num_stages is None or num_stages < 1:
        logger.error("Could not determine number of stages from Claude output")
        raise SmithersError("Could not determine number of stages from Claude output")

    logger.info(f"Planning complete: {num_stages} stages")
    print_success(f"Planning complete. TODO file created with {num_stages} stages.")
    return PlanResult(todo_file=todo_file, num_stages=num_stages, design_content=design_content)


def implement(
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
    base_branch: Annotated[
        str,
        typer.Option("--base", "-b", help="Base branch to create PRs against"),
    ] = "main",
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Claude model to use"),
    ] = "claude-opus-4-5-20251101",
    todo_file: Annotated[
        Path | None,
        typer.Option(
            "--todo-file",
            "-t",
            help="Existing TODO plan file to use instead of running planning",
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    branch_prefix: Annotated[
        str,
        typer.Option(
            "--branch-prefix",
            "-p",
            help="Prefix for branch names (e.g., 'username/' for 'username/stage-1-models')",
        ),
    ] = "",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without executing"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    resume: Annotated[
        bool,
        typer.Option("--resume", "-r", help="Resume from checkpoint - skip completed stages"),
    ] = False,
) -> None:
    """Implement a design document as staged PRs.

    This command analyzes a design document and creates an implementation plan,
    then executes each stage in parallel where possible, creating PRs for review.
    """
    print_random_quote()

    logger.info("=" * 60)
    logger.info("Starting implement command")
    logger.info(f"  design_doc: {design_doc}")
    logger.info(f"  base_branch: {base_branch}")
    logger.info(f"  model: {model}")
    logger.info(f"  todo_file: {todo_file}")
    logger.info(f"  branch_prefix: {branch_prefix}")
    logger.info(f"  dry_run: {dry_run}")
    logger.info(f"  verbose: {verbose}")
    logger.info(f"  resume: {resume}")
    logger.info("=" * 60)

    # Set up configuration
    config = Config(
        model=model,
        base_branch=base_branch,
        branch_prefix=branch_prefix,
        dry_run=dry_run,
        verbose=verbose,
    )
    set_config(config)

    # Initialize services
    git_service = GitService()
    tmux_service = TmuxService()
    claude_service = ClaudeService(model=model)

    # Check dependencies
    logger.info("Checking dependencies")
    try:
        tmux_service.ensure_rejoinable_session(
            session_name=f"smithers-impl-{design_doc.stem}",
            argv=sys.argv,
        )
        git_service.ensure_dependencies()
        tmux_service.ensure_dependencies()
        claude_service.ensure_dependencies()
        logger.info("All dependencies satisfied")
    except DependencyMissingError as e:
        logger.exception("Missing dependencies")
        print_error(str(e))
        console.print("\nInstall with:")
        console.print("  git clone https://github.com/coderabbitai/git-worktree-runner.git")
        console.print("  (cd git-worktree-runner && ./install.sh)  # installs git gtr")
        console.print("  brew install tmux")
        console.print("  npm install -g @anthropic-ai/claude-code")
        raise typer.Exit(1) from e

    user_supplied_todo = todo_file is not None
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    todo_file_path = todo_file or config.plans_dir / f"{design_doc.stem}.smithers-{timestamp}.md"
    todo_file_path.parent.mkdir(parents=True, exist_ok=True)

    print_header("Smithers: Implementing Design Document")
    console.print(f"Design doc: [cyan]{design_doc}[/cyan]")
    console.print(f"TODO file: [cyan]{todo_file_path}[/cyan]")
    console.print(f"Base branch: [cyan]{base_branch}[/cyan]")
    if branch_prefix:
        console.print(f"Branch prefix: [cyan]{branch_prefix}[/cyan]")
    console.print(f"Model: [cyan]{model}[/cyan]")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        return

    # Track collected PRs for fix mode transition
    collected_prs: list[int] = []
    design_content: str | None = None

    try:
        if user_supplied_todo:
            logger.info("Using existing TODO file, skipping planning phase")
            console.print("\n[yellow]Using existing TODO file; skipping planning phase.[/yellow]")
            design_content = design_doc.read_text()
            logger.info("Phase 2: Implementation")
            print_header("PHASE 2: IMPLEMENTATION")
            collected_prs = _run_implementation_phase(
                design_doc=design_doc,
                design_content=design_content,
                todo_file=todo_file_path,
                base_branch=base_branch,
                git_service=git_service,
                tmux_service=tmux_service,
                claude_service=claude_service,
                config=config,
                resume=resume,
            )
        else:
            logger.info("Phase 1: Planning")
            print_header("PHASE 1: PLANNING")
            plan_result = run_planning_session(
                design_doc=design_doc,
                todo_file=todo_file_path,
                claude_service=claude_service,
                config=config,
            )
            design_content = plan_result.design_content

            logger.info("Phase 2: Implementation")
            print_header("PHASE 2: IMPLEMENTATION")
            collected_prs = _run_implementation_phase(
                design_doc=design_doc,
                design_content=design_content,
                todo_file=todo_file_path,
                base_branch=base_branch,
                git_service=git_service,
                tmux_service=tmux_service,
                claude_service=claude_service,
                config=config,
                resume=resume,
            )
    except SmithersError as e:
        logger.error(f"SmithersError: {e}", exc_info=True)
        print_error(str(e))
        raise typer.Exit(1) from e
    finally:
        # Cleanup worktrees on exit
        logger.info("Cleanup: removing worktrees and killing sessions")
        git_service.cleanup_all_worktrees()
        tmux_service.kill_all_smithers_sessions()

    # Report results
    print_header("Implementation Complete!")
    console.print(f"TODO file: [cyan]{todo_file_path}[/cyan]")
    console.print(f"PRs created: [green]{', '.join(f'#{pr}' for pr in collected_prs)}[/green]")

    # Transition to fix mode if we have PRs
    if collected_prs:
        print_info("\nAutomatically transitioning to FIX mode...")
        # Import here to avoid circular import
        from smithers.commands.fix import fix as fix_command

        fix_command(
            design_doc=design_doc,
            pr_identifiers=[str(pr) for pr in collected_prs],
            model=model,
            dry_run=dry_run,
            verbose=verbose,
        )
    else:
        console.print("\n[yellow]No PRs created. Run fix mode manually if needed.[/yellow]")


def _run_implementation_phase(
    design_doc: Path,
    design_content: str,
    todo_file: Path,
    base_branch: str,
    git_service: GitService,
    tmux_service: TmuxService,
    claude_service: ClaudeService,
    config: Config,
    resume: bool = False,
) -> list[int]:
    """Run the implementation phase - execute stages by parallel group.

    Args:
        design_doc: Path to the design document.
        design_content: Content of the design document.
        todo_file: Path to the TODO file.
        base_branch: Base branch name.
        git_service: Git service instance.
        tmux_service: Tmux service instance.
        claude_service: Claude service instance.
        config: Configuration instance.
        resume: If True, skip stages that are already completed.

    Returns:
        List of PR numbers created (including previously completed if resuming).
    """
    logger.info(
        f"Starting implementation phase: todo_file={todo_file}, "
        f"base_branch={base_branch}, resume={resume}"
    )
    todo = TodoFile.parse(todo_file)
    parallel_groups = todo.get_parallel_groups_in_order()

    if not parallel_groups:
        logger.info("No parallel groups found, using sequential execution")
        console.print("[yellow]No parallel groups found. Using sequential execution.[/yellow]")
        parallel_groups = ["sequential"]

    logger.info(f"Parallel groups: {parallel_groups}")
    console.print(f"Parallel groups to process: [cyan]{', '.join(parallel_groups)}[/cyan]")

    # Initialize the TODO updater for checkpointing
    todo_updater = TodoUpdater(todo_file)

    collected_prs: list[int] = []

    # Handle resume mode - collect PRs from already completed stages
    if resume:
        completed_stages = todo.get_completed_stages()
        if completed_stages:
            completed_nums = [s.number for s in completed_stages]
            for stage in completed_stages:
                if stage.pr_number:
                    collected_prs.append(stage.pr_number)
                    logger.info(
                        f"Resume: Including existing PR #{stage.pr_number} "
                        f"from Stage {stage.number}"
                    )
            console.print(
                f"[cyan]Resume mode: Skipping {len(completed_stages)} completed stage(s): "
                f"{completed_nums}[/cyan]"
            )
    else:
        # Warn if there are completed stages but not resuming
        completed_stages = todo.get_completed_stages()
        if completed_stages:
            completed_nums = [s.number for s in completed_stages]
            logger.warning(f"Found completed stages {completed_nums} but --resume not specified")
            console.print(
                f"[yellow]Warning: Found {len(completed_stages)} completed stage(s) "
                f"{completed_nums}. Use --resume to skip them, or they will be re-run.[/yellow]"
            )

    from smithers.models.stage import StageStatus

    for group in parallel_groups:
        logger.info(f"Processing parallel group: {group}")
        print_header(f"PROCESSING PARALLEL GROUP: {group}")

        all_stages_in_group = todo.get_stages_by_group().get(group, [])

        # Filter out completed stages when in resume mode
        if resume:
            stages_in_group = [s for s in all_stages_in_group if s.status != StageStatus.COMPLETED]
            skipped_count = len(all_stages_in_group) - len(stages_in_group)
            if skipped_count > 0:
                logger.info(f"Skipping {skipped_count} completed stage(s) in group {group}")
                console.print(
                    f"[dim]Skipping {skipped_count} completed stage(s) in group {group}[/dim]"
                )
        else:
            stages_in_group = all_stages_in_group

        if not stages_in_group:
            logger.info(f"No stages to process for group {group}")
            console.print(f"[dim]Group {group}: all stages completed, skipping[/dim]")
            continue

        logger.info(f"Group {group} has {len(stages_in_group)} stages to process")

        # Prepare worktrees and prompts for all stages
        group_data: list[StageData] = []
        todo_content = todo_file.read_text()

        for stage in stages_in_group:
            logger.info(f"Preparing Stage {stage.number}: branch={stage.branch}")
            console.print(f"Preparing Stage {stage.number} (branch: {stage.branch})")

            # Determine base for worktree (depends_on is now the actual branch name)
            worktree_base = git_service.get_branch_dependency_base(
                stage.depends_on,
                base_branch,
            )

            # Create worktree
            worktree_path = git_service.create_worktree(stage.branch, worktree_base)

            # Create prompt file
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
            prompt_file = config.temp_dir / f"smithers-stage-{stage.number}-{timestamp}.prompt"
            output_file = prompt_file.with_suffix(".prompt.output")
            exit_file = prompt_file.with_suffix(".prompt.exit")

            # Generate implementation prompt
            prompt = render_implementation_prompt(
                stage_number=stage.number,
                branch=stage.branch,
                worktree_path=worktree_path,
                worktree_base=worktree_base,
                design_doc_path=design_doc,
                design_content=design_content,
                todo_file_path=todo_file,
                todo_content=todo_content,
            )
            prompt_file.write_text(prompt)

            group_data.append(
                {
                    "stage": stage,
                    "worktree_path": worktree_path,
                    "prompt_file": prompt_file,
                    "output_file": output_file,
                    "exit_file": exit_file,
                }
            )

        # Mark all stages in this group as in_progress before launching
        stage_numbers = [data["stage"].number for data in group_data]
        todo_updater.mark_stages_in_progress(stage_numbers)
        console.print(f"Marked stages {stage_numbers} as in_progress")

        # Launch all Claude sessions in parallel
        console.print(f"\nLaunching {len(group_data)} Claude session(s) in parallel...")

        sessions: list[str] = []
        for data in group_data:
            command = claude_service.create_tmux_command(
                prompt_file=data["prompt_file"],
                output_file=data["output_file"],
                exit_file=data["exit_file"],
            )

            session = tmux_service.create_session(
                name=data["stage"].branch,
                workdir=data["worktree_path"],
                command=command,
            )
            sessions.append(session)
            console.print(f"  Stage {data['stage'].number}: tmux session '{session}'")

        # Wait for all sessions
        tmux_service.wait_for_sessions(sessions, poll_interval=config.poll_interval)

        # Collect results
        logger.info("Collecting results from all stages")
        console.print("\nCollecting results...")
        for data in group_data:
            stage = data["stage"]
            output_file = data["output_file"]
            prompt_file = data["prompt_file"]
            exit_file = data["exit_file"]

            if output_file.exists():
                output = output_file.read_text()
                logger.debug(f"Stage {stage.number} output ({len(output)} chars)")

                if config.verbose:
                    print_header(f"OUTPUT FROM STAGE {stage.number}")
                    console.print(output)

                # Extract PR number from JSON (with fallback to legacy regex)
                from smithers.services.claude import ClaudeResult

                stage_result = ClaudeResult(output=output, exit_code=0, success=True)
                json_output = stage_result.extract_json()

                pr_num: int | None = None
                if json_output:
                    pr_num = json_output.get("pr_number")
                    logger.debug(f"Stage {stage.number} JSON output: {json_output}")
                else:
                    # Fallback to legacy regex format
                    import re

                    pr_match = re.search(rf"STAGE_{stage.number}_PR:\s*(\d+)", output)
                    if pr_match:
                        pr_num = int(pr_match.group(1))

                if pr_num:
                    collected_prs.append(pr_num)
                    logger.info(f"Stage {stage.number} complete: PR #{pr_num}")
                    print_success(f"Stage {stage.number} complete. PR #{pr_num}")

                    # Update TODO file with completed status and PR number
                    todo_updater.update_stage_status(
                        stage_number=stage.number,
                        status=StageStatus.COMPLETED,
                        pr_number=pr_num,
                    )
                else:
                    msg = f"Could not extract PR number for Stage {stage.number}"
                    logger.warning(msg)
                    console.print(f"[yellow]Warning: {msg}[/yellow]")
                    # Stage stays as in_progress - user needs to investigate
                    console.print(
                        f"[yellow]Stage {stage.number} kept as in_progress - "
                        f"verify completion manually[/yellow]"
                    )
            else:
                logger.warning(f"No output file found for Stage {stage.number}: {output_file}")
                console.print(
                    f"[yellow]Warning: No output file found for Stage {stage.number}[/yellow]"
                )
                # Stage stays as in_progress - user needs to investigate
                console.print(
                    f"[yellow]Stage {stage.number} kept as in_progress - "
                    f"verify completion manually[/yellow]"
                )

            # Cleanup temp files
            for f in [prompt_file, output_file, exit_file]:
                if f.exists():
                    f.unlink()

        # Cleanup worktrees for this group
        for data in group_data:
            git_service.cleanup_worktree(data["stage"].branch)

        print_success(f"Group {group} complete.")

    return collected_prs
