# Agent Guidelines

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
