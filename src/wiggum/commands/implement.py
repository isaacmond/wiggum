"""Implement command - creates staged PRs from a design document."""

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, TypedDict

import typer

from wiggum.console import console, print_error, print_header, print_info, print_success
from wiggum.exceptions import DependencyMissingError, WiggumError
from wiggum.models.config import Config, set_config
from wiggum.models.todo import TodoFile
from wiggum.prompts.implementation import render_implementation_prompt
from wiggum.prompts.planning import render_planning_prompt
from wiggum.services.claude import ClaudeService
from wiggum.services.git import GitService
from wiggum.services.tmux import TmuxService

if TYPE_CHECKING:
    from wiggum.models.stage import Stage


class StageData(TypedDict):
    """Type definition for stage data dictionary."""

    stage: Stage
    worktree_path: Path
    prompt_file: Path
    output_file: Path
    exit_file: Path


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
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without executing"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Implement a design document as staged PRs.

    This command analyzes a design document and creates an implementation plan,
    then executes each stage in parallel where possible, creating PRs for review.
    """
    # Set up configuration
    config = Config(
        model=model,
        base_branch=base_branch,
        dry_run=dry_run,
        verbose=verbose,
    )
    set_config(config)

    # Initialize services
    git_service = GitService()
    tmux_service = TmuxService()
    claude_service = ClaudeService(model=model)

    # Check dependencies
    try:
        git_service.ensure_dependencies()
        tmux_service.ensure_dependencies()
        claude_service.ensure_dependencies()
    except DependencyMissingError as e:
        print_error(str(e))
        console.print("\nInstall with:")
        console.print("  brew install coderabbitai/tap/gtr  # git-worktree-runner")
        console.print("  brew install tmux")
        console.print("  npm install -g @anthropic-ai/claude-code")
        raise typer.Exit(1) from e

    # Create timestamped TODO file path
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    todo_file = design_doc.with_suffix(f".wiggum-{timestamp}.md")

    print_header("Wiggum: Implementing Design Document")
    console.print(f"Design doc: [cyan]{design_doc}[/cyan]")
    console.print(f"TODO file: [cyan]{todo_file}[/cyan]")
    console.print(f"Base branch: [cyan]{base_branch}[/cyan]")
    console.print(f"Model: [cyan]{model}[/cyan]")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        return

    # Track collected PRs for fix mode transition
    collected_prs: list[int] = []

    try:
        # Phase 1: Planning
        print_header("PHASE 1: PLANNING")
        collected_prs = _run_planning_phase(
            design_doc=design_doc,
            todo_file=todo_file,
            base_branch=base_branch,
            git_service=git_service,
            tmux_service=tmux_service,
            claude_service=claude_service,
            config=config,
        )
    except WiggumError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    finally:
        # Cleanup worktrees on exit
        git_service.cleanup_all_worktrees()
        tmux_service.kill_all_wiggum_sessions()

    # Report results
    print_header("Implementation Complete!")
    console.print(f"TODO file: [cyan]{todo_file}[/cyan]")
    console.print(f"PRs created: [green]{', '.join(f'#{pr}' for pr in collected_prs)}[/green]")

    # Transition to fix mode if we have PRs
    if collected_prs:
        print_info("\nAutomatically transitioning to FIX mode...")
        # Import here to avoid circular import
        from wiggum.commands.fix import fix as fix_command

        fix_command(
            design_doc=design_doc,
            pr_numbers=collected_prs,
            model=model,
            dry_run=dry_run,
            verbose=verbose,
        )
    else:
        console.print("\n[yellow]No PRs created. Run fix mode manually if needed.[/yellow]")


def _run_planning_phase(
    design_doc: Path,
    todo_file: Path,
    base_branch: str,
    git_service: GitService,
    tmux_service: TmuxService,
    claude_service: ClaudeService,
    config: Config,
) -> list[int]:
    """Run the planning phase - create TODO file and implement stages.

    Returns:
        List of PR numbers created
    """
    design_content = design_doc.read_text()

    # Generate planning prompt
    planning_prompt = render_planning_prompt(
        design_doc_path=design_doc,
        design_content=design_content,
        todo_file_path=todo_file,
    )

    print_info("Running Claude Code for planning...")
    result = claude_service.run_prompt(planning_prompt)

    if config.verbose:
        console.print(result.output)

    if not result.success:
        raise WiggumError(f"Claude Code failed during planning: {result.output}")

    # Verify TODO file was created
    if not todo_file.exists():
        raise WiggumError(f"TODO file was not created at {todo_file}")

    # Extract number of stages
    num_stages = result.extract_int("NUM_STAGES")
    if num_stages is None or num_stages < 1:
        raise WiggumError("Could not determine number of stages from Claude output")

    print_success(f"Planning complete. TODO file created with {num_stages} stages.")

    # Phase 2: Implementation
    print_header("PHASE 2: IMPLEMENTATION")
    return _run_implementation_phase(
        design_doc=design_doc,
        design_content=design_content,
        todo_file=todo_file,
        base_branch=base_branch,
        git_service=git_service,
        tmux_service=tmux_service,
        claude_service=claude_service,
        config=config,
    )


def _run_implementation_phase(
    design_doc: Path,
    design_content: str,
    todo_file: Path,
    base_branch: str,
    git_service: GitService,
    tmux_service: TmuxService,
    claude_service: ClaudeService,
    config: Config,
) -> list[int]:
    """Run the implementation phase - execute stages by parallel group.

    Returns:
        List of PR numbers created
    """
    todo = TodoFile.parse(todo_file)
    parallel_groups = todo.get_parallel_groups_in_order()

    if not parallel_groups:
        console.print("[yellow]No parallel groups found. Using sequential execution.[/yellow]")
        parallel_groups = ["sequential"]

    console.print(f"Parallel groups to process: [cyan]{', '.join(parallel_groups)}[/cyan]")

    collected_prs: list[int] = []

    # Build stage number -> branch mapping for dependency resolution
    stages_data: dict[int, str] = {stage.number: stage.branch for stage in todo.stages}

    for group in parallel_groups:
        print_header(f"PROCESSING PARALLEL GROUP: {group}")

        stages_in_group = todo.get_stages_by_group().get(group, [])
        if not stages_in_group:
            console.print(f"[yellow]No stages found for group {group}[/yellow]")
            continue

        # Prepare worktrees and prompts for all stages
        group_data: list[StageData] = []
        todo_content = todo_file.read_text()

        for stage in stages_in_group:
            console.print(f"Preparing Stage {stage.number} (branch: {stage.branch})")

            # Determine base for worktree
            worktree_base = git_service.get_branch_dependency_base(
                stage.depends_on,
                stages_data,
                base_branch,
            )

            # Create worktree
            worktree_path = git_service.create_worktree(stage.branch, worktree_base)

            # Create prompt file
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
            prompt_file = config.temp_dir / f"wiggum-stage-{stage.number}-{timestamp}.prompt"
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
        console.print("\nCollecting results...")
        for data in group_data:
            stage = data["stage"]
            output_file = data["output_file"]
            prompt_file = data["prompt_file"]
            exit_file = data["exit_file"]

            if output_file.exists():
                output = output_file.read_text()

                if config.verbose:
                    print_header(f"OUTPUT FROM STAGE {stage.number}")
                    console.print(output)

                # Extract PR number
                import re

                pr_match = re.search(rf"STAGE_{stage.number}_PR:\s*(\d+)", output)
                if pr_match:
                    pr_num = int(pr_match.group(1))
                    collected_prs.append(pr_num)
                    print_success(f"Stage {stage.number} complete. PR #{pr_num}")
                else:
                    msg = f"Could not extract PR number for Stage {stage.number}"
                    console.print(f"[yellow]Warning: {msg}[/yellow]")
            else:
                console.print(
                    f"[yellow]Warning: No output file found for Stage {stage.number}[/yellow]"
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
