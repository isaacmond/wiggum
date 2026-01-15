"""Vibekanban MCP service for task tracking."""

import asyncio
import json
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from smithers.logging_config import get_logger
from smithers.services.config_loader import load_vibekanban_config

logger = get_logger("smithers.services.vibekanban")

# Path where vibe-kanban stores its port file
VIBE_KANBAN_PORT_FILE = Path(tempfile.gettempdir()) / "vibe-kanban" / "vibe-kanban.port"


@dataclass
class VibekanbanService:
    """Service for interacting with Vibekanban's MCP server.

    All operations fail gracefully - they log warnings but never raise exceptions.
    This ensures smithers continues working even if vibekanban is unavailable.
    """

    project_id: str | None = None
    enabled: bool = True

    def is_configured(self) -> bool:
        """Check if vibekanban is configured and enabled."""
        return self.enabled and self.project_id is not None

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the vibekanban MCP server.

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Arguments to pass to the tool

        Returns:
            Tool result as a dictionary, or empty dict on failure
        """
        # Suppress all vibe-kanban noise (npm warnings + rust debug logs)
        server_params = StdioServerParameters(
            command="sh",
            args=["-c", "npx --quiet vibe-kanban@latest --mcp 2>/dev/null"],
        )

        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

            # Extract text content from result
            for content in result.content:
                if hasattr(content, "text"):
                    text_value = str(content.text)
                    # Try to parse as JSON
                    try:
                        return json.loads(text_value)
                    except json.JSONDecodeError:
                        return {"text": text_value}

            return {}

    def create_task(
        self,
        title: str,
        description: str = "",
        status: str = "in_progress",
    ) -> str | None:
        """Create a task in vibekanban.

        Args:
            title: Task title
            description: Task description
            status: Initial task status (default: "in_progress")

        Returns:
            Task ID if successful, None otherwise.
        """
        if not self.is_configured():
            logger.debug("Vibekanban not configured, skipping task creation")
            return None

        try:
            # Note: create_task MCP tool only accepts project_id, title, description
            # Tasks are created in "todo" status by default
            result = asyncio.run(
                self._call_tool(
                    "create_task",
                    {
                        "project_id": self.project_id,
                        "title": title,
                        "description": description,
                    },
                )
            )
            task_id = result.get("task_id") or result.get("id")
            if task_id:
                task_id_str = str(task_id)
                logger.info(f"Created vibekanban task: {task_id_str}")
                # Set initial status via update_task (create_task doesn't support status)
                if status != "todo":
                    self.update_task_status(task_id_str, status)
                return task_id_str
            logger.warning(f"No task_id in vibekanban response: {result}")
            return None
        except Exception:
            logger.warning("Failed to create vibekanban task", exc_info=True)
            return None

    def update_task(
        self,
        task_id: str,
        status: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Update a task's fields.

        Args:
            task_id: The task ID
            status: New status (e.g., "in_progress", "completed", "failed")
            title: New task title
            description: New task description

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_configured() or not task_id:
            return False

        try:
            arguments: dict[str, Any] = {"task_id": task_id}
            if status is not None:
                arguments["status"] = status
            if title is not None:
                arguments["title"] = title
            if description is not None:
                arguments["description"] = description

            asyncio.run(self._call_tool("update_task", arguments))

            updates = []
            if status:
                updates.append(f"status={status}")
            if title:
                updates.append(f"title={title}")
            if description:
                updates.append("description=...")
            logger.info(f"Updated vibekanban task {task_id}: {', '.join(updates)}")
            return True
        except Exception:
            logger.warning(f"Failed to update vibekanban task {task_id}", exc_info=True)
            return False

    def update_task_status(
        self,
        task_id: str,
        status: str,
    ) -> bool:
        """Update a task's status.

        Args:
            task_id: The task ID
            status: New status (e.g., "in_progress", "completed", "failed")

        Returns:
            True if successful, False otherwise.
        """
        return self.update_task(task_id, status=status)

    def list_projects(self) -> list[dict[str, str]]:
        """List all vibekanban projects.

        Returns:
            List of project dicts with 'id' and 'name' keys, or empty list on failure.
        """
        try:
            result = asyncio.run(
                self._call_tool(
                    "list_projects",
                    {},
                )
            )
            projects = result.get("projects", [])
            if isinstance(projects, list):
                return projects
            return []
        except Exception:
            logger.warning("Failed to list vibekanban projects", exc_info=True)
            return []

    def list_tasks(self, status: str) -> list[dict[str, str]]:
        """List tasks in the project.

        Args:
            status: Status filter (e.g., "in_progress", "todo")

        Returns:
            List of task dicts, or empty list on failure.
        """
        if not self.is_configured():
            return []

        try:
            args: dict[str, str] = {"project_id": str(self.project_id), "status": status}
            result = asyncio.run(self._call_tool("list_tasks", args))
            tasks = result.get("tasks", [])
            if isinstance(tasks, list):
                return tasks
            return []
        except Exception:
            logger.warning("Failed to list vibekanban tasks", exc_info=True)
            return []

    def delete_task(self, task_id: str) -> bool:
        """Delete a task from vibekanban.

        Args:
            task_id: The task ID to delete

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_configured() or not task_id:
            return False

        try:
            asyncio.run(self._call_tool("delete_task", {"task_id": task_id}))
            logger.info(f"Deleted vibekanban task: {task_id}")
            return True
        except Exception:
            logger.warning(f"Failed to delete vibekanban task {task_id}", exc_info=True)
            return False

    def list_all_smithers_tasks(self) -> list[dict[str, str]]:
        """List all smithers-created tasks across all statuses.

        Finds tasks with titles starting with [impl] or [fix] in any status.

        Returns:
            List of task dicts, or empty list on failure.
        """
        if not self.is_configured():
            return []

        smithers_tasks: list[dict[str, str]] = []
        statuses = ["todo", "in_progress", "completed", "failed"]

        for status in statuses:
            try:
                tasks = self.list_tasks(status=status)
                for task in tasks:
                    title = task.get("title", "")
                    if title.startswith(("[impl]", "[fix]")):
                        smithers_tasks.append(task)
            except Exception:
                logger.warning(f"Failed to list tasks with status {status}", exc_info=True)

        return smithers_tasks

    def cleanup_orphaned_tasks(self) -> int:
        """Mark orphaned in_progress [impl] and [fix] tasks as failed.

        Finds tasks with titles starting with [impl] or [fix] that are
        still in_progress (from previous interrupted sessions) and marks
        them as failed.

        Returns:
            Number of tasks cleaned up.
        """
        if not self.is_configured():
            return 0

        cleaned = 0
        try:
            tasks = self.list_tasks(status="in_progress")
            for task in tasks:
                title = task.get("title", "")
                task_id = task.get("id")
                # Only clean up smithers-created tasks
                if (
                    task_id
                    and title.startswith(("[impl]", "[fix]"))
                    and self.update_task_status(task_id, "failed")
                ):
                    logger.info(f"Cleaned up orphaned task: {task_id} ({title})")
                    cleaned += 1
        except Exception:
            logger.warning("Failed to cleanup orphaned tasks", exc_info=True)

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} orphaned vibekanban task(s)")
        return cleaned


def _is_vibekanban_running() -> bool:
    """Check if vibe-kanban backend is running.

    Returns:
        True if vibe-kanban is running, False otherwise.
    """
    if not VIBE_KANBAN_PORT_FILE.exists():
        return False

    # Port file exists, try to connect to verify it's actually running
    try:
        port = VIBE_KANBAN_PORT_FILE.read_text().strip()
        url = f"http://127.0.0.1:{port}/api/projects"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def get_vibekanban_url() -> str | None:
    """Get the vibekanban web UI URL if running.

    Returns:
        URL string (e.g., "http://127.0.0.1:3000") if running, None otherwise.
    """
    if not VIBE_KANBAN_PORT_FILE.exists():
        return None

    try:
        port = VIBE_KANBAN_PORT_FILE.read_text().strip()
        if port:
            return f"http://127.0.0.1:{port}"
    except Exception:
        pass
    return None


def _launch_vibekanban() -> bool:
    """Launch vibe-kanban in the background if not running.

    Returns:
        True if vibe-kanban is now running, False otherwise.
    """
    if _is_vibekanban_running():
        logger.debug("vibe-kanban already running")
        return True

    logger.info("Launching vibe-kanban...")
    try:
        # Launch vibe-kanban in background, suppressing output
        subprocess.Popen(
            ["npx", "--quiet", "vibe-kanban@latest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for it to start (up to 10 seconds)
        for _ in range(20):
            time.sleep(0.5)
            if _is_vibekanban_running():
                logger.info("vibe-kanban started successfully")
                return True

        logger.warning("vibe-kanban failed to start within timeout")
        return False
    except Exception:
        logger.warning("Failed to launch vibe-kanban", exc_info=True)
        return False


def create_vibekanban_service(cleanup: bool = True) -> VibekanbanService:
    """Create a VibekanbanService from configuration.

    Loads configuration from ~/.smithers/config.json and environment variables.
    Auto-discovers project by matching current directory name to project names.
    Launches vibe-kanban if not already running.

    Args:
        cleanup: If True, mark orphaned in_progress tasks as failed on startup.

    Returns:
        Configured VibekanbanService instance.
    """
    config = load_vibekanban_config()

    if config.enabled:
        # Ensure vibe-kanban is running
        _launch_vibekanban()

    # Always auto-discover project based on current directory
    # (env var or explicit config still takes precedence)
    if config.enabled and not config.project_id:
        config.project_id = _auto_discover_project_id()

    service = VibekanbanService(
        project_id=config.project_id,
        enabled=config.enabled,
    )

    # Cleanup orphaned tasks from previous interrupted sessions
    if cleanup and service.is_configured():
        service.cleanup_orphaned_tasks()

    return service


def _auto_discover_project_id() -> str | None:
    """Auto-discover vibekanban project ID.

    Lists available projects and returns one automatically:
    - First, try to match the current directory name to a project name
    - If no match, use the first project if only one exists
    - If multiple projects and no match, return None (don't guess)

    Returns:
        Project ID if found, None otherwise.
    """
    logger.debug("Auto-discovering vibekanban project ID...")

    # Create a temporary service without project_id to list projects
    service = VibekanbanService(enabled=True, project_id=None)
    projects = service.list_projects()

    if not projects:
        logger.debug("No vibekanban projects found")
        return None

    # Try to match current directory name to a project
    current_dir = Path.cwd().name
    logger.debug(f"Looking for project matching directory: {current_dir}")

    for project in projects:
        project_name = project.get("name", "")
        if project_name == current_dir:
            project_id = project.get("id")
            logger.info(f"Auto-selected vibekanban project: {project_name} ({project_id})")
            return project_id

    # No match found - only auto-select if there's exactly one project
    if len(projects) == 1:
        project = projects[0]
        project_id = project.get("id")
        name = project.get("name", "unknown")
        logger.info(f"Auto-selected vibekanban project (only one available): {name} ({project_id})")
        return project_id

    # Multiple projects and no directory match - don't guess
    logger.debug(f"No vibekanban project matches directory '{current_dir}', skipping")
    return None
