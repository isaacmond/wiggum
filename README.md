# Smithers

Your loyal PR automation assistant, powered by Claude AI.

Like Mr. Burns' ever-faithful assistant, Smithers diligently handles the details of creating staged PRs from design documents and iteratively fixes review comments until everything passes. Excellent.

## Warning

**This tool runs Claude Code with `--dangerously-skip-permissions` enabled by default.** This means:

- Claude will execute commands, create/modify/delete files, and make git operations **without asking for confirmation**
- The AI has full access to your repository and can make any changes it deems necessary
- PRs are created and pushed to your repository automatically

**Use at your own risk.** Only run Smithers in repositories where you are comfortable with autonomous AI-driven changes. Review all generated PRs carefully before merging. It is strongly recommended to run this tool in isolated environments or on branches you can safely discard.

## Features

- **Implement Mode**: Analyzes design documents and creates stacked PRs executed sequentially
- **Fix Mode**: Loops until all review comments are addressed and CI passes (PRs processed in parallel)
- **Plan Mode**: Interactively create implementation plans with Claude before implementing
- **Streaming Output**: See real-time output while sessions run in the background; Ctrl+C to detach without stopping
- **Session Management**: Rejoin running tmux sessions after detaching or disconnecting
- **Checkpoint & Resume**: Automatically saves progress; resume interrupted runs with `--resume`
- **Git Worktrees**: Uses isolated worktrees for clean implementation
- **Claude AI Powered**: Leverages Claude Code CLI for intelligent code generation

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

</details>

## Usage

### Implement a Design Document

```bash
# Create staged PRs from a design document
# Branch names will be prefixed with your git user's first name (e.g., isaac/stage-1-models)
smithers implement docs/my-feature.md --base main

# With custom branch prefix
smithers implement docs/my-feature.md --branch-prefix myprefix/

# With custom model
smithers implement docs/my-feature.md --model claude-sonnet-4-20250514

# Use an existing plan file (skip planning phase)
smithers implement docs/my-feature.md --todo-file ~/.smithers/plans/my-plan.md

# Resume an interrupted run (skip completed stages)
smithers implement docs/my-feature.md --todo-file ~/.smithers/plans/my-plan.md --resume
```

### Fix PR Review Comments

```bash
# Fix review comments on specific PRs
smithers fix docs/my-feature.md 123 124 125

# Also accepts GitHub PR URLs
smithers fix docs/my-feature.md https://github.com/owner/repo/pull/123

# With max iterations limit
smithers fix docs/my-feature.md 123 --max-iterations 5
```

### Standardize PR Titles and Descriptions

```bash
# Standardize a series of related PRs with consistent titles and descriptions
smithers standardize 123 124 125

# Also accepts GitHub PR URLs
smithers standardize https://github.com/owner/repo/pull/123 124 125

# Dry run - show analysis without modifying PRs
smithers standardize 123 124 125 --dry-run
```

Analyzes all PR diffs to understand the overall feature, then updates each PR with:
- Consistent titles: `Feature Name (1/3): Description`
- Overview and summary of changes
- Table of all PRs in the series
- Dependency information

### Interactive Planning

```bash
# Interactively create an implementation plan with Claude
smithers plan

# With custom output path
smithers plan --output ~/plans/my-feature.md
```

Creates a plan file via an interactive Claude session that can later be used with `smithers implement --todo-file`.

### Session Management

Smithers runs long operations in background tmux sessions while streaming output to your terminal in real-time. This means:

- **You see all output** as it happens, just like running a command directly
- **Press Ctrl+C to detach** without stopping the session - it continues in the background
- **Reconnect anytime** with `smithers rejoin` if you detach or get disconnected

```bash
# List all running smithers tmux sessions
smithers sessions

# Rejoin the most recent session (streaming mode with Ctrl+C to detach)
smithers rejoin

# Rejoin a specific session
smithers rejoin smithers-impl-my-feature

# Rejoin with full terminal control (Ctrl+B D to detach)
smithers rejoin --attach

# List sessions via rejoin command
smithers rejoin --list

# Kill the most recent session
smithers kill

# Kill a specific session
smithers kill smithers-impl-my-feature

# Kill all running smithers sessions
smithers kill --all

# Also remove git worktrees created by the session
smithers kill --cleanup-worktrees

# Skip confirmation prompt
smithers kill --force
```

### Updates

Smithers automatically updates itself when a new minor or patch version is available. When you run any command, it checks for updates and installs them in the background.

For major version updates, you'll see a warning and can manually update:

```bash
smithers update
```

### Common Options

| Option | Short | Description | Commands |
|--------|-------|-------------|----------|
| `--model` | `-m` | Claude model to use (default: claude-opus-4-5-20251101) | all |
| `--base` | `-b` | Base branch for PRs (default: main) | implement |
| `--todo-file` | `-t` | Existing plan file to use | implement |
| `--branch-prefix` | `-p` | Prefix for branch names (default: git user's first name, e.g., `isaac/`) | implement |
| `--resume` | `-r` | Resume from checkpoint, skip completed stages | implement |
| `--max-iterations` | | Max fix iterations, 0=unlimited (default: 0) | fix |
| `--dry-run` | `-n` | Show what would be done without executing | implement, fix |
| `--verbose` | `-v` | Enable verbose output | all |

## How It Works

### Plan Mode

1. **Interactive Session**: Launches Claude in plan mode for collaborative planning
2. **Plan Creation**: Work with Claude to design your implementation approach
3. **Output**: Saves the plan file for later use with `smithers implement --todo-file`

### Implement Mode

1. **Planning Phase**: Claude analyzes the design document and creates a TODO file with implementation stages (or uses an existing plan file)
2. **Implementation Phase**:
   - Stages are executed sequentially (one at a time)
   - Git worktrees are created for each stage
   - Claude runs in a tmux session for each stage
   - Stacked PRs are created for each stage
   - **Checkpointing**: Stage status and PR numbers are saved to the TODO file as each stage completes
3. **Transition**: Automatically transitions to Fix mode with created PRs

#### Detaching and Resuming

You can safely detach from a running session at any time:

- **Press Ctrl+C** to detach - the session continues running in the background
- **Close your terminal** - the session keeps running
- **Lose your connection** - no problem, the session persists

To reconnect or resume:

```bash
# Rejoin the running tmux session (if still active)
smithers rejoin

# Or resume using the checkpoint in the TODO file
smithers implement docs/my-feature.md --todo-file ~/.smithers/plans/my-feature.smithers-*.md --resume
```

The `--resume` flag skips stages already marked as `completed` in the TODO file and includes their PR numbers in the final output.

### Fix Mode

1. **Fetch Comments**: Gets unresolved review comments and CI failures for each PR
2. **Process PRs**: Creates worktrees and runs Claude in parallel to address issues
3. **Loop**: Continues until ALL of the following are satisfied:
   - Base branch (origin/main) is merged into all PR branches
   - All merge conflicts are resolved
   - All review comments are addressed (0 unresolved comments per PR)
   - All CI/CD checks are passing

**Note**: Fix mode always updates PR branches with the latest changes from the base branch and resolves merge conflicts, even when there are no review comments to address.

## Architecture

Smithers uses a **prompt-first architecture** where Claude Code handles all the complex logic:

- **Prompts do the heavy lifting**: Implementation, PR creation, review fixes, and CI debugging are all handled by detailed prompts
- **Python handles orchestration**: Git worktrees, tmux sessions, and loop control
- **Structured JSON output**: Claude returns structured JSON for reliable parsing
- **Works with any GitHub repo**: Automatically detects the current repository

## Development

```bash
cd smithers

# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check src/ tests/

# Run type checking
uv run ty check src/

# Format code
uv run ruff format src/ tests/
```

## License

MIT
