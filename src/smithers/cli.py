"""Smithers CLI - Your loyal PR automation assistant, powered by Claude AI."""

import typer
from rich.console import Console

from smithers import __version__
from smithers.commands.fix import fix
from smithers.commands.implement import implement
from smithers.commands.kill import kill
from smithers.commands.plan import plan
from smithers.commands.quote import quote
from smithers.commands.rejoin import rejoin
from smithers.commands.sessions import sessions
from smithers.commands.standardize import standardize
from smithers.commands.update import update
from smithers.logging_config import (
    cleanup_old_logs,
    cleanup_old_sessions,
    get_logger,
    setup_logging,
)
from smithers.services.version import check_for_updates

# Create the Typer app
app = typer.Typer(
    name="smithers",
    help="Your loyal PR automation assistant, powered by Claude AI.",
    add_completion=False,
    rich_markup_mode="rich",
)

# Add commands
app.command(name="plan")(plan)
app.command(name="implement")(implement)
app.command(name="fix")(fix)
app.command(name="standardize")(standardize)
app.command(name="rejoin")(rejoin)
app.command(name="sessions")(sessions)
app.command(name="kill")(kill)
app.command(name="update")(update)
app.command(name="quote", hidden=True)(quote)


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
    # Initialize logging early
    setup_logging()
    cleanup_old_logs(max_age_days=30)
    cleanup_old_sessions(max_age_days=7)

    logger = get_logger("smithers.cli")

    if version:
        console = Console()
        console.print(f"smithers version {__version__}")
        check_for_updates()
        raise typer.Exit()

    # Check for updates on every invocation
    check_for_updates()

    # Log the command being invoked
    if ctx.invoked_subcommand:
        logger.info(f"Command invoked: {ctx.invoked_subcommand}")

    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        console = Console()
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
