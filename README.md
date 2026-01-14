# Wiggum

Automate PR creation and review fixing with Claude AI.

Named after Chief Wiggum's dogged persistence, this tool implements design documents as staged PRs and iteratively fixes review comments until everything passes.

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

# Install wiggum (from local clone)
uv tool install /path/to/wiggum
```

## Usage

### Implement a Design Document

```bash
# Create staged PRs from a design document
wiggum implement docs/my-feature.md --base main

# With custom model
wiggum implement docs/my-feature.md --model claude-sonnet-4-20250514
```

### Fix PR Review Comments

```bash
# Fix review comments on specific PRs
wiggum fix docs/my-feature.md 123 124 125

# With max iterations limit
wiggum fix docs/my-feature.md 123 --max-iterations 5
```

### Options

```
--model, -m    Claude model to use (default: claude-opus-4-5-20251101)
--base, -b     Base branch for PRs (default: main)
--dry-run, -n  Show what would be done without executing
--verbose, -v  Enable verbose output
```

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

## Development

```bash
cd wiggum

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
