# Troubleshooting

## Logs

Smithers logs to `~/.smithers/logs/`. Each run creates a timestamped log file:

```bash
ls -la ~/.smithers/logs/
tail -f ~/.smithers/logs/smithers-*.log  # Follow current log
```

Logs are automatically cleaned up after 30 days.

## Session Issues

### Session won't start

If smithers hangs when starting a session:

```bash
# Check if tmux is running
tmux ls

# Kill any stuck smithers sessions
smithers kill --all

# Or manually
tmux kill-server
```

### Can't rejoin session

```bash
# List all tmux sessions
tmux ls

# Rejoin directly via tmux
tmux attach -t <session-name>
```

### Disable tmux wrapper

For debugging, you can disable the tmux session wrapper:

```bash
export SMITHERS_DISABLE_TMUX_WRAPPER=1
smithers implement docs/feature.md --branch-prefix test/
```

This runs Claude directly in your terminal instead of a background tmux session.

## Worktree Issues

### Worktrees not cleaned up

If worktrees are left behind after a crash:

```bash
# List all worktrees
git worktree list

# Remove a specific worktree
git worktree remove <path> --force

# Prune stale worktree references
git worktree prune
```

### Branch already exists

If you see "branch already exists" errors:

```bash
# Delete local branch
git branch -D <branch-name>

# Delete remote branch
git push origin --delete <branch-name>
```

## Claude Issues

### Claude not found

Ensure Claude Code CLI is installed:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

### Claude rate limited

If Claude is rate limited, smithers will retry automatically. For persistent issues, wait a few minutes or check your Anthropic API quota.

### Claude output not parsed

If smithers can't extract PR numbers or status from Claude output, check the verbose output:

```bash
smithers implement docs/feature.md --branch-prefix test/ --verbose
```

## GitHub Issues

### Authentication failed

Ensure GitHub CLI is authenticated:

```bash
gh auth status
gh auth login  # If needed
```

### PR not found

Verify the PR exists and you have access:

```bash
gh pr view <pr-number>
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SMITHERS_DISABLE_TMUX_WRAPPER` | Set to `1` to run Claude directly without tmux |
| `SMITHERS_VIBEKANBAN_ENABLED` | Set to `false` to disable vibekanban integration |
| `SMITHERS_VIBEKANBAN_PROJECT_ID` | Override the vibekanban project ID |

## Getting Help

1. Check the logs at `~/.smithers/logs/`
2. Run with `--verbose` for detailed output
3. Report issues at https://github.com/isaacmond/smithers/issues
