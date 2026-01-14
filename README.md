# Smithers

Your loyal PR automation assistant, powered by Claude AI.

Like Mr. Burns' ever-faithful assistant, Smithers diligently handles the details of creating staged PRs from design documents and iteratively fixes review comments until everything passes. Excellent.

## Features

- **Implement Mode**: Analyzes design documents and creates staged PRs with parallel execution
- **Fix Mode**: Loops until all review comments are addressed and CI passes
- **Parallel Execution**: Uses git worktrees and tmux for concurrent stage implementation
- **Claude AI Powered**: Leverages Claude Code CLI for intelligent code generation

## Installation

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) - Package manager
- [git-worktree-runner (git gtr)](https://github.com/coderabbitai/git-worktree-runner) - Worktree management
- [tmux](https://github.com/tmux/tmux) - Terminal multiplexer
- [Claude Code CLI](https://claude.ai/code) - AI code generation
- [GitHub CLI (gh)](https://cli.github.com/) - GitHub operations

```bash
# Install git-worktree-runner (gtr)
git clone https://github.com/coderabbitai/git-worktree-runner.git
(cd git-worktree-runner && ./install.sh)

# Install other prerequisites
brew install tmux
brew install gh
npm install -g @anthropic-ai/claude-code

# Install smithers (from local clone)
uv tool install /path/to/smithers
```

## Usage

### Implement a Design Document

```bash
# Create staged PRs from a design document
smithers implement docs/my-feature.md --base main

# With custom model
smithers implement docs/my-feature.md --model claude-sonnet-4-20250514
```

### Fix PR Review Comments

```bash
# Fix review comments on specific PRs
smithers fix docs/my-feature.md 123 124 125

# With max iterations limit
smithers fix docs/my-feature.md 123 --max-iterations 5
```

### Options

```
--model, -m    Claude model to use (default: claude-opus-4-5-20251101)
--base, -b     Base branch for PRs (default: main)
--dry-run, -n  Show what would be done without executing
--verbose, -v  Enable verbose output
```

### Update Smithers

```bash
# Update to the latest released version
smithers update

# Alias
smithers update-self
```

The update command uses `uv tool upgrade smithers` under the hood. Ensure `uv` is installed and on your `PATH`.

## How It Works

### Implement Mode

1. **Planning Phase**: Claude analyzes the design document and creates a TODO file with implementation stages
2. **Implementation Phase**:
   - Stages are grouped by parallel group
   - Git worktrees are created for each stage
   - Claude runs in parallel tmux sessions
   - PRs are created for each stage
3. **Transition**: Automatically transitions to Fix mode with created PRs

### Fix Mode

1. **Fetch Comments**: Gets unresolved review comments and CI failures for each PR
2. **Process PRs**: Creates worktrees and runs Claude in parallel to address issues
3. **Loop**: Continues until all comments are resolved and CI passes

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
