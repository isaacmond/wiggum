"""Cleanup command - delete all smithers-created vibekanban tasks."""

from typing import Annotated

import typer

from smithers.console import console, print_error, print_header, print_info, print_success
from smithers.services.vibekanban import VibekanbanService, get_vibekanban_url


def cleanup(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Delete all smithers-created vibekanban tasks.

    Finds and deletes all tasks with [impl] or [fix] prefixes across
    all statuses (todo, in_progress, completed, failed).
    """
    print_header("Vibekanban Cleanup")

    vibekanban_url = get_vibekanban_url()
    if vibekanban_url:
        console.print(f"URL: [cyan]{vibekanban_url}[/cyan]\n")

    service = VibekanbanService(enabled=True)

    # Auto-discover project if not configured
    if not service.project_id:
        from smithers.services.vibekanban import _auto_discover_project_id

        service.project_id = _auto_discover_project_id()

    if not service.is_configured():
        print_error("No vibekanban project configured.")
        console.print("\nRun [cyan]smithers projects[/cyan] to see available projects.")
        raise typer.Exit(1)

    # Find all smithers-created tasks
    console.print("[dim]Scanning for smithers-created tasks...[/dim]\n")
    tasks = service.list_all_smithers_tasks()

    if not tasks:
        print_info("No smithers-created tasks found.")
        return

    # Group tasks by status for display
    by_status: dict[str, list[dict[str, str]]] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(task)

    # Display what will be deleted
    console.print(f"[yellow]Found {len(tasks)} smithers-created task(s):[/yellow]\n")

    for status, status_tasks in sorted(by_status.items()):
        console.print(f"  [dim]{status}:[/dim]")
        for task in status_tasks:
            task_id = task.get("id", "unknown")
            title = task.get("title", "Untitled")
            console.print(f"    - [cyan]{title}[/cyan] [dim]({task_id})[/dim]")
        console.print()

    # Confirm before deleting (unless --force)
    if not force:
        confirm = typer.confirm(f"Delete all {len(tasks)} task(s)?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    # Delete each task
    console.print()
    deleted = 0
    failed = 0

    for task in tasks:
        task_id = task.get("id")
        title = task.get("title", "Untitled")

        if not task_id:
            continue

        if service.delete_task(task_id):
            console.print(f"  [red]x[/red] Deleted: [cyan]{title}[/cyan]")
            deleted += 1
        else:
            console.print(f"  [yellow]![/yellow] Failed to delete: [cyan]{title}[/cyan]")
            failed += 1

    console.print()
    if deleted > 0:
        print_success(f"Deleted {deleted} task(s).")
    if failed > 0:
        print_error(f"Failed to delete {failed} task(s).")
