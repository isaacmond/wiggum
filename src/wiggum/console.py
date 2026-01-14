"""Rich console singleton and helpers for terminal output."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Global console instance
console = Console()


def print_header(title: str) -> None:
    """Print a styled header."""
    console.print()
    console.print(Panel(title, style="bold blue"))
    console.print()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]Error: {message}[/red]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning: {message}[/yellow]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]{message}[/blue]")


def create_status_table(title: str) -> Table:
    """Create a table for displaying status information."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    return table


def create_progress() -> Progress:
    """Create a progress bar for tracking long-running operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )
