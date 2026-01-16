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
Before pushing changes, run ALL quality checks (e.g. lint, type check, test)

Fix ALL issues. Do NOT push or declare completion until all pass.
"""

SELF_HEALING_SECTION = """
### Error Handling & Retries (REQUIRED)
If any command or operation fails, you MUST handle it:

1. **Diagnose the error**: Is it permissions? Network? Syntax? Rate limit?
2. **Retry with alternative approach**: Try different flags, commands, or strategies
3. **Maximum 5 attempts**: Make up to 5 attempts before declaring failure
4. **Adaptive waiting**: For rate limits, wait 30-60 seconds before retry

Common retryable scenarios:
- `gh` CLI errors → try with different flags or wait for rate limit
- Git push rejected → pull/merge first, then retry
- CI flaky → re-run the check: `gh run rerun <run_id> --failed`
- Network timeout → wait and retry

Only report failure in your JSON output after exhausting all 5 attempts.
"""

STRICT_JSON_SECTION = """
### Output Format (CRITICAL)
You MUST output valid JSON at the END of your response between the delimiters shown below.

**Requirements:**
- JSON must be valid and parseable
- All fields must be present (use null for unknown values)
- If you encounter an unrecoverable error, still output JSON with:
  - Set completion/done fields to false
  - Add "error": "<description of what went wrong>"
- Failure to output valid JSON is a critical error
"""

TODO_STATE_SECTION = """
### TODO File State Management (REQUIRED)
You own the TODO file state for your stage. At specific points:

**At START of your session:**
1. Read the TODO file (path given above)
2. Find your stage (number given above)
3. Update its **Status** from `pending` to `in_progress`
4. Save the file

**At END of your session (success):**
1. Update your stage's **Status** to `completed`
2. Fill in the **PR** field with the PR number
3. Check off completed acceptance criteria
4. Save the file

**At END of your session (failure after 5 retries):**
1. Update your stage's **Status** to `failed`
2. Add a note explaining what went wrong
3. Save the file
"""

POST_PR_WORKFLOW_SECTION = """
### Post-PR Code Quality Workflow (REQUIRED)
After creating your PR, you MUST immediately run these three steps in order.
Commit any improvements from each step as separate commits before proceeding to the next.

**Step 1 - Simplify:** Say exactly: "Use the code-simplifier subagent to review and simplify the code I just wrote"

**Step 2 - De-slopify:** Say exactly: "Use the de-slopify skill to remove any AI-generated slop patterns from my changes"

**Step 3 - Review:** Say exactly: "Use the code-review subagent to review my changes"

Do not consider the PR ready for review until all three steps are complete.
"""
