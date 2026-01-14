"""Rejoin command - reattach to a previous smithers tmux session."""

from typing import Annotated

import typer

from smithers.console import console, print_error, print_header, print_info
from smithers.exceptions import TmuxError
from smithers.services.tmux import TmuxService


def rejoin(
    session: Annotated[
        str | None,
        typer.Argument(
            help="Session name to rejoin (defaults to the last smithers session)",
        ),
    ] = None,
    list_sessions: Annotated[
        bool,
        typer.Option("--list", "-l", help="List all running smithers sessions"),
    ] = False,
) -> None:
    """Rejoin a running smithers tmux session.

    If no session name is provided, rejoins the most recent smithers session.
    Use --list to see all running smithers sessions.
    """
    tmux_service = TmuxService()

    # List mode
    if list_sessions:
        _list_sessions(tmux_service)
        return

    # Determine which session to rejoin
    target_session: str | None = session

    if target_session is None:
        # Try to get the last session from hint file
        last_session = tmux_service.get_last_session()
        if last_session:
            target_session = last_session.session_name
            print_info(f"Rejoining last session: {target_session}")
            if last_session.started:
                console.print(f"  Started: [dim]{last_session.started}[/dim]")
        else:
            # Fall back to listing available sessions
            sessions = tmux_service.list_smithers_sessions()
            if not sessions:
                print_error("No smithers sessions found.")
                console.print("\nStart a new session with:")
                console.print("  [cyan]smithers implement <design-doc>[/cyan]")
                console.print("  [cyan]smithers fix <design-doc> <pr-numbers>[/cyan]")
                raise typer.Exit(1)

            if len(sessions) == 1:
                target_session = sessions[0].name
                print_info(f"Found one session: {target_session}")
            else:
                console.print("\n[yellow]Multiple sessions found. Please specify one:[/yellow]\n")
                _list_sessions(tmux_service)
                raise typer.Exit(1)

    # Verify the session exists
    if not tmux_service.session_exists(target_session):
        print_error(f"Session '{target_session}' no longer exists.")

        # Show available sessions if any
        sessions = tmux_service.list_smithers_sessions()
        if sessions:
            console.print("\nAvailable sessions:")
            for s in sessions:
                attached = " [green](attached)[/green]" if s.attached else ""
                console.print(f"  • {s.name}{attached}")
        raise typer.Exit(1)

    # Attach to the session
    try:
        console.print(f"\n[bold green]Attaching to session:[/bold green] {target_session}")
        console.print("[dim]Use Ctrl+B D to detach without stopping the session[/dim]\n")
        exit_code = tmux_service.attach_session(target_session)
        raise typer.Exit(exit_code)
    except TmuxError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


def _list_sessions(tmux_service: TmuxService) -> None:
    """List all running smithers tmux sessions."""
    sessions = tmux_service.list_smithers_sessions()

    if not sessions:
        console.print("[yellow]No running smithers sessions found.[/yellow]")
        console.print("\nStart a new session with:")
        console.print("  [cyan]smithers implement <design-doc>[/cyan]")
        console.print("  [cyan]smithers fix <design-doc> <pr-numbers>[/cyan]")
        return

    print_header("Running Smithers Sessions")

    for session in sessions:
        attached = " [green](attached)[/green]" if session.attached else ""
        windows = f"{session.windows} window{'s' if session.windows != 1 else ''}"
        console.print(f"  • [cyan]{session.name}[/cyan] - {windows}{attached}")

    console.print("\n[dim]Rejoin with:[/dim] smithers rejoin <session-name>")
    console.print("[dim]Or just:[/dim] smithers rejoin  [dim](for the most recent)[/dim]")
