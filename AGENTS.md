# Agent Guidelines

## Code Style

- **NEVER** use `from __future__ import annotations` or any other `__future__` imports
- **ALWAYS** put all imports at module level (top of file) — no inline or local imports inside functions

## Required Checks

All checks must pass before pushing to `main`. Run all checks with auto-fix:

```bash
./fix.sh
```

This formats code, fixes lint issues, runs type checking, and runs tests.

## Shipping Code

Ship directly to `main` — no PRs required when checks pass:

1. Run all checks (above)
2. Update README.md with new functionality
3. Bump version and release (below)
4. Push to `main`

## Releasing a New Version

1. **Update version** in both `pyproject.toml` and `src/smithers/__init__.py` (must match)

2. **Run all checks**, then commit:
   ```bash
   git add pyproject.toml src/smithers/__init__.py uv.lock
   git commit -m "Bump version to X.Y.Z"
   ```

3. **Tag and push**:
   ```bash
   git tag X.Y.Z
   git push origin main
   git push origin X.Y.Z
   ```
