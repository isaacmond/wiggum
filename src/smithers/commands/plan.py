"""Plan command - interactively create an implementation plan with Claude."""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.exceptions import DependencyMissingError, SmithersError
from smithers.logging_config import get_logger
from smithers.models.config import Config, set_config
from smithers.services.claude import ClaudeService
from smithers.services.vibekanban import create_vibekanban_service, get_vibekanban_url

logger = get_logger("smithers.commands.plan")


def plan(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output path for the plan file (default: ~/.smithers/plans/)",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Claude model to use"),
    ] = "claude-opus-4-5-20251101",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
) -> None:
    """Interactively create an implementation plan with Claude.

    This command launches Claude in plan mode to help you create a detailed
    implementation plan. The resulting plan file can then be used with
    'smithers implement <design_doc> --todo-file <plan>'.
    """
    print_random_quote()

    logger.info("=" * 60)
    logger.info("Starting plan command")
    logger.info(f"  output: {output}")
    logger.info(f"  model: {model}")
    logger.info(f"  verbose: {verbose}")
    logger.info("=" * 60)

    # Set up configuration (branch_prefix not used in interactive planning mode)
    config = Config(
        branch_prefix="",
        verbose=verbose,
    )
    set_config(config)

    # Initialize services for dependency check
    claude_service = ClaudeService(model=model)
    vibekanban_service = create_vibekanban_service()

    # Check dependencies
    logger.info("Checking dependencies")
    try:
        claude_service.ensure_dependencies()
        logger.info("All dependencies satisfied")
    except DependencyMissingError as e:
        logger.exception("Missing dependencies")
        print_error(str(e))
        console.print("\nInstall with:")
        console.print("  npm install -g @anthropic-ai/claude-code")
        raise typer.Exit(1) from e

    print_header("Smithers: Interactive Planning Mode")
    console.print(f"Model: [cyan]{model}[/cyan]")
    vibekanban_url = get_vibekanban_url()
    if vibekanban_url:
        console.print(f"Vibekanban: [cyan]{vibekanban_url}[/cyan]")

    # Determine output path
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    output_path = output or config.plans_dir / f"plan.smithers-{timestamp}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Output path: {output_path}")
    console.print(f"Plan will be saved to: [cyan]{output_path}[/cyan]")

    # The plan file Claude will create during the session
    claude_plan_file = Path.cwd() / ".claude" / "plan.md"
    logger.debug(f"Claude plan file: {claude_plan_file}")

    # Create vibekanban task for tracking (uses [plan] prefix like [impl] and [fix])
    vk_task_id = vibekanban_service.find_or_create_task(
        title=f"[plan] {output_path.stem}",
        description="Interactive planning session with Claude",
    )
    if vk_task_id:
        logger.info(f"Created/reused vibekanban task: {vk_task_id}")

    print_info("\nLaunching Claude in plan mode...")
    print_info("Work with Claude to create your implementation plan.")
    print_info("When finished, exit Claude (Ctrl+C or /exit).\n")

    # Build the Claude command for interactive plan mode
    # Use --append-system-prompt to tell Claude to output the plan path and copy to ~/Downloads
    # instead of starting implementation when the plan is accepted
    append_prompt = (
        "IMPORTANT: When the user accepts a plan in plan mode, do NOT start implementing. "
        "Instead:\n"
        "1. Print the full path of the plan file (e.g., .claude/plan.md)\n"
        f"2. Copy the plan file to ~/Downloads/{output_path.name}\n"
        "3. Confirm the copy was successful and exit\n"
        "This allows the user to review and use the plan with smithers implement later."
    )
    cmd = [
        "claude",
        "--model",
        model,
        "--permission-mode",
        "plan",
        "--append-system-prompt",
        append_prompt,
    ]
    logger.info(f"Launching Claude: {' '.join(cmd)}")

    try:
        # Run Claude interactively (no capture, direct terminal access)
        result = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            check=False,
        )

        logger.info(f"Claude exited with code: {result.returncode}")

        if result.returncode not in {0, 130}:
            # 130 is SIGINT (Ctrl+C), which is a normal exit
            logger.warning(f"Claude exited with unexpected code: {result.returncode}")
            console.print(f"[yellow]Claude exited with code {result.returncode}[/yellow]")

    except subprocess.SubprocessError as e:
        logger.exception("Failed to run Claude")
        raise SmithersError(f"Failed to run Claude: {e}") from e

    # Look for the plan file
    if not claude_plan_file.exists():
        logger.error(f"No plan file found at {claude_plan_file}")
        print_error(f"No plan file found at {claude_plan_file}")
        console.print("\nMake sure Claude created a plan during the session.")
        console.print("You can also manually specify a plan file with --output.")
        raise typer.Exit(1)

    # Copy the plan file to the output location
    try:
        shutil.copy2(claude_plan_file, output_path)
        logger.info(f"Plan saved to: {output_path}")
        print_success(f"\nPlan saved to: {output_path}")
        console.print("\nTo implement this plan, run:")
        console.print(f"  [cyan]smithers implement <design_doc> --todo-file {output_path}[/cyan]")

        # Update vibekanban task status
        if vk_task_id:
            vibekanban_service.update_task_status(vk_task_id, "completed")
    except OSError as e:
        logger.exception("Failed to copy plan file")
        if vk_task_id:
            vibekanban_service.update_task_status(vk_task_id, "failed")
        raise SmithersError(f"Failed to copy plan file: {e}") from e
