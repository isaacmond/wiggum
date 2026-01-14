"""Self-update command for smithers."""

import subprocess
from shutil import which

import typer

from smithers.commands.quote import print_random_quote
from smithers.console import console, print_error, print_info, print_success


def update() -> None:
    """
    Update smithers to the latest available version using uv.

    This runs `uv tool upgrade smithers` under the hood.
    """
    print_random_quote()

    if which("uv") is None:
        print_error("uv is required to update smithers. Install it from https://docs.astral.sh/uv/")
        raise typer.Exit(1)

    print_info("Updating smithers with `uv tool upgrade smithers`...")

    try:
        result = subprocess.run(
            ["uv", "tool", "upgrade", "smithers"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = stderr or stdout or "uv failed to upgrade smithers."
        print_error(f"Update failed: {message}")
        raise typer.Exit(exc.returncode) from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        console.print(stdout)
    if stderr:
        console.print(stderr)

    success_message = (
        "Smithers is already up to date."
        if "already" in stdout.lower()
        else "Smithers updated successfully."
    )
    print_success(f"{success_message} Restart your shell if the old version is still active.")

    # Ensure the process exits with success for Typer when used as a subcommand.
    raise typer.Exit(code=0)
