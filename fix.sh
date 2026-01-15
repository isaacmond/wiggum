#!/bin/bash
# Run all CI checks with auto-fix enabled where applicable

set -e

echo "=== Formatting code ==="
uv run ruff format src/ tests/

echo ""
echo "=== Fixing lint issues ==="
uv run ruff check --fix src/ tests/

echo ""
echo "=== Type checking ==="
uv run ty check src/

echo ""
echo "=== Running tests ==="
uv run pytest tests/

echo ""
echo "=== All checks passed! ==="
