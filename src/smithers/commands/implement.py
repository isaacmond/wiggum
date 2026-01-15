"""Implement command - creates staged PRs from a design document."""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.exceptions import DependencyMissingError, SmithersError
from smithers.logging_config import get_logger, get_session_log_file
from smithers.models.config import Config, set_config
from smithers.models.todo import TodoFile
from smithers.prompts.implementation import render_implementation_prompt
from smithers.prompts.planning import render_planning_prompt
from smithers.services.claude import ClaudeService
from smithers.services.git import GitService
from smithers.services.tmux import TmuxService
from smithers.services.vibekanban import (
    VibekanbanService,
    create_vibekanban_service,
    get_vibekanban_url,
)

logger = get_logger("smithers.commands.implement")


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
    branch_prefix: Annotated[
        str,
        typer.Option(
            "--branch-prefix",
            "-p",
            help="Prefix for branch names (e.g., 'username/' for 'username/stage-1-models')",
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
    then executes each stage sequentially, creating stacked PRs for review.
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
    vibekanban_service = create_vibekanban_service()

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

    # Session name for PR tracking
    session_name = f"smithers-impl-{design_doc.stem}"

    # Ensure session directory exists for PR tracking
    session_dir = config.sessions_dir / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    print_header("Smithers: Implementing Design Document")
    console.print(f"Design doc: [cyan]{design_doc}[/cyan]")
    console.print(f"TODO file: [cyan]{todo_file_path}[/cyan]")
    console.print(f"Base branch: [cyan]{base_branch}[/cyan]")
    console.print(f"Branch prefix: [cyan]{branch_prefix}[/cyan]")
    console.print(f"Model: [cyan]{model}[/cyan]")
    vibekanban_url = get_vibekanban_url()
    if vibekanban_url:
        console.print(f"Vibekanban: [cyan]{vibekanban_url}[/cyan]")

    # Print log and output locations
    console.print(f"Log file: [cyan]{get_session_log_file()}[/cyan]")
    console.print(f"Claude output dir: [cyan]{config.temp_dir}[/cyan]")

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
                vibekanban_service=vibekanban_service,
                config=config,
                resume=resume,
                session_name=session_name,
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
                vibekanban_service=vibekanban_service,
                config=config,
                resume=resume,
                session_name=session_name,
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
    vibekanban_service: VibekanbanService,
    config: Config,
    resume: bool = False,
    session_name: str = "",
) -> list[int]:
    """Run the implementation phase - execute stages sequentially.

    Args:
        design_doc: Path to the design document.
        design_content: Content of the design document.
        todo_file: Path to the TODO file.
        base_branch: Base branch name.
        git_service: Git service instance.
        tmux_service: Tmux service instance.
        claude_service: Claude service instance.
        vibekanban_service: Vibekanban service for task tracking.
        config: Configuration instance.
        resume: If True, skip stages that are already completed.
        session_name: The smithers session name for PR tracking.

    Returns:
        List of PR numbers created (including previously completed if resuming).
    """
    logger.info(
        f"Starting implementation phase: todo_file={todo_file}, "
        f"base_branch={base_branch}, resume={resume}"
    )
    todo = TodoFile.parse(todo_file)

    logger.info(f"Found {len(todo.stages)} stages to process sequentially")
    console.print(f"Stages to process: [cyan]{len(todo.stages)}[/cyan] (sequential execution)")

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

    # Process each stage sequentially
    for stage in todo.stages:
        # Skip completed stages when in resume mode
        if resume and stage.status == StageStatus.COMPLETED:
            logger.info(f"Skipping completed Stage {stage.number}")
            console.print(f"[dim]Skipping completed Stage {stage.number}[/dim]")
            continue

        logger.info(f"Processing Stage {stage.number}")
        print_header(f"PROCESSING STAGE {stage.number}: {stage.title}")

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

        # Re-read TODO content for each stage (may have been updated)
        todo_content = todo_file.read_text()

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
            session_name=session_name,
        )
        prompt_file.write_text(prompt)

        # Create vibekanban task for this stage session (created as in_progress)
        stage_vk_task_id = vibekanban_service.create_task(
            title=f"[impl] Stage {stage.number}: {stage.title}",
            description=f"Implementing {stage.branch} for {design_doc.name}",
        )
        if stage_vk_task_id:
            logger.info(f"Created vibekanban task for stage {stage.number}: {stage_vk_task_id}")

        # Launch Claude session (Claude will mark stage as in_progress)
        console.print(f"\nLaunching Claude session for Stage {stage.number}...")

        command = claude_service.create_tmux_command(
            prompt_file=prompt_file,
            output_file=output_file,
            exit_file=exit_file,
        )

        session = tmux_service.create_session(
            name=stage.branch,
            workdir=worktree_path,
            command=command,
        )
        console.print(f"  Stage {stage.number}: tmux session '{session}'")

        # Wait for session to complete
        tmux_service.wait_for_sessions([session], poll_interval=config.poll_interval)

        # Collect result
        logger.info(f"Collecting result from Stage {stage.number}")
        console.print("\nCollecting result...")

        if output_file.exists():
            output = output_file.read_text()
            logger.debug(f"Stage {stage.number} output ({len(output)} chars)")

            if config.verbose:
                print_header(f"OUTPUT FROM STAGE {stage.number}")
                console.print(output)

            # Extract PR number using multiple strategies
            from smithers.services.claude import ClaudeResult

            stage_result = ClaudeResult(output=output, exit_code=0, success=True)
            pr_num = stage_result.extract_pr_number()
            logger.debug(f"Stage {stage.number} extracted PR number: {pr_num}")

            if pr_num:
                collected_prs.append(pr_num)
                logger.info(f"Stage {stage.number} complete: PR #{pr_num}")
                print_success(f"Stage {stage.number} complete. PR #{pr_num}")
                # Update vibekanban task status to completed
                if stage_vk_task_id:
                    vibekanban_service.update_task_status(stage_vk_task_id, "completed")
            else:
                msg = f"Could not extract PR number for Stage {stage.number}"
                logger.warning(msg)
                console.print(f"[yellow]Warning: {msg}[/yellow]")
                # Stage stays as in_progress - user needs to investigate
                console.print(
                    f"[yellow]Stage {stage.number} kept as in_progress - "
                    f"verify completion manually[/yellow]"
                )
                # Update vibekanban task status to failed
                if stage_vk_task_id:
                    vibekanban_service.update_task_status(stage_vk_task_id, "failed")
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
            # Update vibekanban task status to failed
            if stage_vk_task_id:
                vibekanban_service.update_task_status(stage_vk_task_id, "failed")

        # Cleanup temp files
        for f in [prompt_file, output_file, exit_file]:
            if f.exists():
                f.unlink()

        # Cleanup worktree for this stage
        git_service.cleanup_worktree(stage.branch)

        print_success(f"Stage {stage.number} complete.")

    return collected_prs
