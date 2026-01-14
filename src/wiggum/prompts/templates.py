"""Base template utilities for prompt generation."""


def render_template(template: str, **kwargs: object) -> str:
    """Render a template string with the given variables.

    Uses simple string formatting with {variable} syntax.

    Args:
        template: The template string
        **kwargs: Variables to substitute

    Returns:
        The rendered string
    """
    return template.format(**kwargs)


# Common sections used across prompts

MERGE_CONFLICT_SECTION = """
### Merge Conflict Resolution (REQUIRED)
When you encounter merge conflicts, you MUST resolve them completely:

1. **Detect conflicts**: After merging, check for conflict markers (<<<<<<< , =======, >>>>>>>)
2. **Understand both sides**: Read the incoming changes and the current branch changes
3. **Make intelligent decisions**:
   - If both sides added different code, keep both (in logical order)
   - If both sides modified the same line, choose the most complete/correct version
   - If one side deleted and one modified, prefer the modification unless deletion was intentional
   - When in doubt, prefer the incoming (base branch) changes for bug fixes, prefer current branch for new features
4. **Remove ALL conflict markers**: Ensure no <<<<<<< , =======, or >>>>>>> remain in any file
5. **Verify the result**: The merged code must be syntactically valid and logically coherent
6. **Stage resolved files**: git add <resolved_files>
7. **Complete the merge**: git commit (or continue rebase if rebasing)

NEVER leave conflict markers in the code. NEVER skip conflict resolution. ALWAYS verify quality checks pass after resolving conflicts.
"""

QUALITY_CHECKS_SECTION = """
### Quality Checks (REQUIRED)
Before pushing changes, run ALL quality checks:
- bin/run_lint.sh
- bin/run_type_check.sh
- bin/run_test.sh

Fix ALL issues. Do NOT push or declare completion until all pass.
"""
