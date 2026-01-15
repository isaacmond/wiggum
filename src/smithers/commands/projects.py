"""Projects command - list vibekanban projects."""

from smithers.console import console, print_header
from smithers.services.vibekanban import VibekanbanService


def projects() -> None:
    """List all vibekanban projects.

    Shows available projects and their IDs for configuration.
    """
    print_header("Vibekanban Projects")

    service = VibekanbanService(enabled=True)
    project_list = service.list_projects()

    if not project_list:
        console.print("[yellow]No projects found or vibekanban unavailable.[/yellow]")
        console.print("\nMake sure vibekanban is installed:")
        console.print("  [cyan]npx vibe-kanban[/cyan]")
        return

    for project in project_list:
        project_id = project.get("id", "unknown")
        name = project.get("name", "Unnamed")
        console.print(f"  • [cyan]{name}[/cyan]  [dim]id:[/dim] {project_id}")

    console.print("\n[dim]Configure with:[/dim]")
    console.print("  [cyan]~/.smithers/config.json[/cyan]:")
    console.print('  [dim]{"vibekanban": {"project_id": "<id>"}}[/dim]')
