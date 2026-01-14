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
from smithers.models.config import Config, set_config
from smithers.services.claude import ClaudeService


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

    # Set up configuration
    config = Config(
        model=model,
        verbose=verbose,
    )
    set_config(config)

    # Initialize services for dependency check
    claude_service = ClaudeService(model=model)

    # Check dependencies
    try:
        claude_service.ensure_dependencies()
    except DependencyMissingError as e:
        print_error(str(e))
        console.print("\nInstall with:")
        console.print("  npm install -g @anthropic-ai/claude-code")
        raise typer.Exit(1) from e

    print_header("Smithers: Interactive Planning Mode")
    console.print(f"Model: [cyan]{model}[/cyan]")

    # Determine output path
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    output_path = output or config.plans_dir / f"plan.smithers-{timestamp}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"Plan will be saved to: [cyan]{output_path}[/cyan]")

    # The plan file Claude will create during the session
    claude_plan_file = Path.cwd() / ".claude" / "plan.md"

    print_info("\nLaunching Claude in plan mode...")
    print_info("Work with Claude to create your implementation plan.")
    print_info("When finished, exit Claude (Ctrl+C or /exit).\n")

    # Build the Claude command for interactive plan mode
    cmd = ["claude", "--model", model, "--plan"]

    try:
        # Run Claude interactively (no capture, direct terminal access)
        result = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            check=False,
        )

        if result.returncode not in {0, 130}:
            # 130 is SIGINT (Ctrl+C), which is a normal exit
            console.print(f"[yellow]Claude exited with code {result.returncode}[/yellow]")

    except subprocess.SubprocessError as e:
        raise SmithersError(f"Failed to run Claude: {e}") from e

    # Look for the plan file
    if not claude_plan_file.exists():
        print_error(f"No plan file found at {claude_plan_file}")
        console.print("\nMake sure Claude created a plan during the session.")
        console.print("You can also manually specify a plan file with --output.")
        raise typer.Exit(1)

    # Copy the plan file to the output location
    try:
        shutil.copy2(claude_plan_file, output_path)
        print_success(f"\nPlan saved to: {output_path}")
        console.print("\nTo implement this plan, run:")
        console.print(f"  [cyan]smithers implement <design_doc> --todo-file {output_path}[/cyan]")
    except OSError as e:
        raise SmithersError(f"Failed to copy plan file: {e}") from e
