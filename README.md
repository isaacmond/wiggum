# Smithers

Your loyal PR automation assistant, powered by Claude AI.

Like Mr. Burns' ever-faithful assistant, Smithers diligently handles the details of creating staged PRs from design documents and iteratively fixes review comments until everything passes. Excellent.

## Warning

**This tool runs Claude Code with `--dangerously-skip-permissions` enabled by default.** This means:

- Claude will execute commands, create/modify/delete files, and make git operations **without asking for confirmation**
- The AI has full access to your repository and can make any changes it deems necessary
- PRs are created and pushed to your repository automatically

**Use at your own risk.** Only run Smithers in repositories where you are comfortable with autonomous AI-driven changes. Review all generated PRs carefully before merging.

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/isaacmond/smithers/main/install.sh | bash
```

That's it! The installer will guide you through setting up any missing dependencies.

<details>
<summary>Manual installation</summary>

If you prefer to install manually:

```bash
# Requires uv (https://docs.astral.sh/uv/)
uv tool install git+https://github.com/isaacmond/smithers.git
```

**Prerequisites:**
- [uv](https://docs.astral.sh/uv/) - Package manager
- [tmux](https://github.com/tmux/tmux) - `brew install tmux`
- [GitHub CLI](https://cli.github.com/) - `brew install gh`
- [Claude Code CLI](https://claude.ai/code) - `npm install -g @anthropic-ai/claude-code`
- `caffeinate` (macOS only, built-in) - Prevents system sleep during long operations

</details>

## Quick Start

```bash
# Implement a design document as staged PRs
smithers implement docs/my-feature.md --branch-prefix myname/

# Fix review comments on existing PRs
smithers fix docs/my-feature.md 123 124 125

# Interactively create a plan with Claude
smithers plan
```

## Commands

### implement

Creates staged PRs from a design document.

```bash
smithers implement docs/my-feature.md --branch-prefix isaac/
smithers implement docs/my-feature.md --branch-prefix isaac/ --base main
smithers implement docs/my-feature.md --branch-prefix isaac/ --model claude-sonnet-4-20250514

# Auto-approve the plan without confirmation
smithers implement docs/my-feature.md --branch-prefix isaac/ --auto-approve

# Use an existing plan file (skip planning phase)
smithers implement docs/my-feature.md --branch-prefix isaac/ --todo-file ~/.smithers/plans/my-plan.md

# Resume an interrupted run
smithers implement docs/my-feature.md --branch-prefix isaac/ --todo-file ~/.smithers/plans/my-plan.md --resume
```

After planning, smithers displays the plan summary and asks for confirmation before proceeding. If no response is received within 5 minutes, the plan is auto-approved. You can provide feedback to revise the plan if needed.

### fix

Loops until all review comments are addressed and CI passes.

```bash
smithers fix docs/my-feature.md 123 124 125
smithers fix docs/my-feature.md https://github.com/owner/repo/pull/123
smithers fix docs/my-feature.md 123 --max-iterations 5
```

### plan

Interactively create an implementation plan with Claude.

```bash
smithers plan
smithers plan --output ~/plans/my-feature.md
```

When you accept a plan, Claude will:
1. Print the full path of the plan file
2. Copy the plan to `~/Downloads/<plan-name>.md`
3. Exit without starting implementation

This allows you to review the plan and use it later with `smithers implement --todo-file`.

### standardize

Standardize PR titles and descriptions for a series of related PRs.

```bash
smithers standardize 123 124 125
smithers standardize 123 124 125 --dry-run  # Preview without modifying
```

Analyzes all PR diffs and updates each PR with:
- Consistent titles: `Feature Name (1/3): Description`
- Overview and summary of changes
- Table of all PRs in the series

### cleanup

Delete all smithers-created vibekanban tasks and optionally git worktrees.

```bash
smithers cleanup                    # Delete all [impl] and [fix] tasks
smithers cleanup megarepo           # Clean up the megarepo project
smithers cleanup --force            # Skip confirmation prompt
smithers cleanup --worktrees        # Also clean up git worktrees
smithers cleanup --worktrees-only   # Only clean up worktrees (skip vibekanban)
smithers cleanup -w --delete-branches  # Remove worktrees and their branches
```

Finds and removes all tasks with `[impl]` or `[fix]` prefixes across all statuses (todo, in_progress, completed, failed). With `--worktrees`, also removes all git worktrees created by smithers (or any other worktrees).

### Session Management

Smithers runs long operations in background tmux sessions while streaming output to your terminal.

- **You see all output** as it happens
- **Press Ctrl+C to detach** without stopping the session
- **Reconnect anytime** with `smithers rejoin`
- **Exit status is recorded** in `~/.smithers/sessions/<session>/exit_code` for reliable completion reporting
- **Caffeinate integration** (macOS): Sessions are wrapped with `caffeinate` to prevent system sleep, ensuring operations complete even during extended runs

```bash
smithers sessions              # List running sessions
smithers rejoin                # Rejoin most recent session
smithers rejoin session-name   # Rejoin specific session
smithers kill                  # Kill most recent session
smithers kill --all            # Kill all sessions
```

When you kill a session, smithers cleans up:
- Git worktrees created by the session
- Plan files associated with the session (so a new execution creates a fresh plan)
- For implement sessions: closes PRs and deletes remote branches

### Monitoring Progress

When starting a new session, smithers displays key file locations:

```
Log file: ~/.smithers/logs/smithers-20250115-143022-abc12345.log
Claude output dir: /tmp
```

Parallel Claude sessions use streaming JSON output for real-time visibility. You can monitor progress:

```bash
# Watch output file grow in real-time
tail -f /tmp/smithers-fix-pr-*.output

# Tail the session log for debugging
tail -f ~/.smithers/logs/smithers-*.log

# With verbose mode, stream logs are preserved for debugging
smithers fix docs/my-feature.md 123 --verbose
# Logs saved to: /tmp/smithers-fix-pr-123-*.stream.log
```

Stream logs contain detailed JSON with:
- Token usage and API costs
- Duration and timing info
- Full conversation history

Session logs in `~/.smithers/logs/` contain:
- All smithers operations and subprocess calls
- Timing and error information for debugging
- Logs are auto-cleaned after 30 days

## Options Reference

| Option | Short | Description | Commands |
|--------|-------|-------------|----------|
| `--branch-prefix` | `-p` | **Required.** Prefix for branch names (e.g., `isaac/`) | implement |
| `--base` | `-b` | Base branch for PRs (default: main) | implement |
| `--todo-file` | `-t` | Existing plan file to use | implement |
| `--resume` | `-r` | Resume from checkpoint, skip completed stages | implement |
| `--auto-approve` | `-y` | Auto-approve the plan without confirmation | implement |
| `--max-iterations` | | Max fix iterations, 0=unlimited (default: 0) | fix |
| `--output` | `-o` | Output path for plan file | plan |
| `--model` | `-m` | Claude model (default: claude-opus-4-5-20251101) | all |
| `--dry-run` | `-n` | Show what would be done without executing | implement, fix, standardize |
| `--verbose` | `-v` | Enable verbose output | all |

## How It Works

### Implement Mode

1. **Planning Phase**: Claude analyzes the design document and creates a TODO file with stages
2. **Plan Approval**: Displays the plan and asks for confirmation (5-minute timeout auto-approves)
   - If rejected, you can provide feedback and Claude will revise the plan
   - Use `--auto-approve` / `-y` to skip confirmation
3. **Implementation Phase**: Executes stages sequentially, creating stacked PRs
4. **Transition**: Automatically runs Fix mode on created PRs

Checkpoints are saved to the TODO file. Use `--resume` to skip completed stages.

### Fix Mode

Loops until ALL conditions are met:
- Base branch is merged into all PR branches
- All merge conflicts resolved
- All review comments addressed (0 unresolved)
- All CI/CD checks passing

Includes robust error handling that logs exceptions during parallel session execution, making it easier to diagnose issues when sessions fail unexpectedly.

## Integrations

### Vibekanban

Smithers integrates with [Vibekanban](https://vibekanban.com/) to track Claude sessions as kanban tasks. Enabled by default with zero configuration.

```bash
smithers projects           # List available projects (shows active)
smithers projects megarepo  # Set megarepo as active project
```

See [docs/vibekanban.md](docs/vibekanban.md) for configuration options.

### Troubleshooting

Having issues? See [docs/troubleshooting.md](docs/troubleshooting.md) for common problems and solutions.

### Updates

Smithers auto-updates for minor and patch versions. For major updates:

```bash
smithers update
```

## Architecture

Smithers uses a **prompt-first architecture**:

- **Prompts do the heavy lifting**: Implementation, PR creation, review fixes handled by detailed prompts
- **Python handles orchestration**: Git worktrees, tmux sessions, loop control
- **Structured JSON output**: Claude returns structured JSON for reliable parsing

## Development

```bash
cd smithers
uv sync --dev

# Run all checks with auto-fix
./fix.sh

# Or individually:
uv run pytest              # Tests
uv run ruff check src/     # Linting
uv run ty check src/       # Type checking
uv run ruff format src/    # Formatting
```

## License

MIT
