# Vibekanban Integration

Smithers integrates with [Vibekanban](https://vibekanban.com/) to track Claude sessions as tasks in a kanban UI. This is enabled by default and requires no configuration.

## Zero Configuration

On first run, smithers will:

1. Auto-discover your vibekanban project
2. Save the project ID to `~/.smithers/config.json` for future runs

To list available projects:

```bash
smithers projects
```

## Manual Configuration (Optional)

If you have multiple projects and want to specify which one to use:

```json
{
  "vibekanban": {
    "project_id": "your-project-id"
  }
}
```

Or use an environment variable:

```bash
export SMITHERS_VIBEKANBAN_PROJECT_ID=your-project-id
```

To disable vibekanban integration:

```bash
export SMITHERS_VIBEKANBAN_ENABLED=false
```

## How It Works

Smithers creates a **separate vibekanban task for each Claude Code session**:

- **Implement mode**: One task per stage (e.g., `[impl] Stage 1: Add models`)
- **Fix mode**: One task per PR (e.g., `[fix] PR #123: feature-branch`)

Each task is:
1. **Created** when the Claude session starts
2. **Set to "in_progress"** while running
3. **Linked to the PR** when available (PR URL is attached to the task)
4. **Marked as "completed"** when the session succeeds
5. **Marked as "failed"** if the session fails

This allows you to monitor individual Claude sessions in real-time through the vibekanban UI, with direct links to the associated PRs.

## Cleanup

To delete all smithers-created tasks from vibekanban:

```bash
smithers cleanup
```

This finds and removes all tasks with `[impl]` or `[fix]` prefixes across all statuses.

## Requirements

- Vibekanban must be installed: `npx vibe-kanban`
