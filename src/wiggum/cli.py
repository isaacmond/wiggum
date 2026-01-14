"""Wiggum CLI - Automate PR creation and review fixing with Claude AI."""

import typer
from rich.console import Console

from wiggum import __version__
from wiggum.commands.fix import fix
from wiggum.commands.implement import implement

# Create the Typer app
app = typer.Typer(
    name="wiggum",
    help="Automate PR creation and review fixing with Claude AI.",
    add_completion=False,
    rich_markup_mode="rich",
)

# Add commands
app.command(name="implement")(implement)
app.command(name="fix")(fix)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        is_eager=True,
    ),
) -> None:
    """Wiggum - The dogged PR automation tool.

    Named after Chief Wiggum's persistent approach to problem-solving,
    this tool automates the creation of staged PRs from design documents
    and iteratively fixes review comments until everything passes.
    """
    if version:
        console = Console()
        console.print(f"wiggum version {__version__}")
        raise typer.Exit()

    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        console = Console()
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
