"""Sessions command - list running smithers tmux sessions."""

from smithers.console import console, print_header
from smithers.services.tmux import TmuxService


def sessions() -> None:
    """List all running smithers tmux sessions.

    Shows all active smithers sessions that you can rejoin.
    """
    tmux_service = TmuxService()
    running_sessions = tmux_service.list_smithers_sessions()

    if not running_sessions:
        console.print("[yellow]No running smithers sessions found.[/yellow]")
        console.print("\nStart a new session with:")
        console.print("  [cyan]smithers implement <design-doc>[/cyan]")
        console.print("  [cyan]smithers fix <design-doc> <pr-numbers>[/cyan]")
        return

    print_header("Running Smithers Sessions")

    for session in running_sessions:
        attached = " [green](attached)[/green]" if session.attached else ""
        windows = f"{session.windows} window{'s' if session.windows != 1 else ''}"
        console.print(f"  • [cyan]{session.name}[/cyan] - {windows}{attached}")

    console.print("\n[dim]Rejoin with:[/dim] smithers rejoin <session-name>")
    console.print("[dim]Or just:[/dim] smithers rejoin  [dim](for the most recent)[/dim]")

    # Show last session hint if available
    last_session = tmux_service.get_last_session()
    if last_session and last_session.started:
        console.print(
            f"\n[dim]Last session:[/dim] [cyan]{last_session.session_name}[/cyan] "
            f"[dim](started {last_session.started})[/dim]"
        )
