"""Smithers CLI - Your loyal PR automation assistant, powered by Claude AI."""

import typer
from rich.console import Console

from smithers import __version__
from smithers.commands.fix import fix
from smithers.commands.implement import implement
from smithers.commands.update import update
from smithers.services.version import check_for_updates

# Create the Typer app
app = typer.Typer(
    name="smithers",
    help="Your loyal PR automation assistant, powered by Claude AI.",
    add_completion=False,
    rich_markup_mode="rich",
)

# Add commands
app.command(name="implement")(implement)
app.command(name="fix")(fix)
app.command(name="update")(update)
# Backwards-compatible alias for self-update
app.command(name="update-self", help="Alias for update")(update)


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
    """Smithers - Your loyal PR automation assistant.

    Like Mr. Burns' ever-faithful assistant, Smithers diligently handles
    the details of creating staged PRs from design documents and iteratively
    fixes review comments until everything passes. Excellent.
    """
    if version:
        console = Console()
        console.print(f"smithers version {__version__}")
        check_for_updates()
        raise typer.Exit()

    # Check for updates on every invocation
    check_for_updates()

    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        console = Console()
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
