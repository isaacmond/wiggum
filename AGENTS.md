# Agent Guidelines

## Code Style

- **NEVER** use `from __future__ import annotations` or any other `__future__` imports

## Before Merging to `main`

**ALWAYS** verify the following checks pass before merging any changes into `main`:

1. **Type checking**
   ```bash
   uv run ty check src/
   ```

2. **Linting**
   ```bash
   uv run ruff check src/
   ```

3. **Tests**
   ```bash
   uv run pytest tests/
   ```

All three checks must pass with no errors before any PR can be merged.

## Releasing a New Version

To release a new version of smithers:

1. **Update version in both locations** (they must match):
   - `pyproject.toml`: Update the `version` field
   - `src/smithers/__init__.py`: Update `__version__`

2. **Run all checks**:
   ```bash
   uv run ty check src/
   uv run ruff check src/
   uv run pytest tests/
   ```

3. **Commit the version bump** (uv.lock is auto-updated by running checks):
   ```bash
   git add pyproject.toml src/smithers/__init__.py uv.lock
   git commit -m "Bump version to X.Y.Z"
   ```

4. **Create and push a git tag**:
   ```bash
   git tag X.Y.Z
   git push origin main
   git push origin X.Y.Z
   ```

The version check feature will use these tags to notify users of available updates.
