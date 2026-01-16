"""Fix phase prompt templates for PR review comments and CI failures."""

from pathlib import Path

from smithers.prompts.templates import (
    MERGE_CONFLICT_SECTION,
    POST_PR_WORKFLOW_SECTION,
    QUALITY_CHECKS_SECTION,
    SELF_HEALING_SECTION,
    STRICT_JSON_SECTION,
    render_template,
)

FIX_PLANNING_PROMPT_TEMPLATE = """You are creating a fix plan to address incomplete implementation, review comments, CI/CD failures and merge issues on pull requests.

## Design Document
Location: {design_doc_path}

{design_content}
{original_todo_section}
## PRs to Process
{pr_numbers}

## Your Task
1. **Check implementation completeness** (if Original Implementation TODO is provided above):
   - Review the PR diffs to see what was actually implemented
   - Compare against the design document and original TODO items
   - Identify any features, functionality, or requirements that are missing or incomplete
   - Note which PR should contain each missing item

2. Fetch the unresolved review comments from each PR using the GitHub CLI:
   - gh pr view <pr_number> --json reviewThreads,comments
   - Use GraphQL to get detailed thread info including resolution status

3. Check CI/CD status for each PR:
   - gh pr checks <pr_number>
   - NEVER wait for CI/CD. If checks are running or pending, assume they PASSED.
   - If any checks are failing, get the failure details:
     - gh run list --branch <branch_name> --limit 1
     - gh run view <run_id> --log-failed
   - Extract the specific test failures, lint errors, or type check errors

4. Check for merge conflicts in each PR

5. Create a TODO file at: {todo_file_path}

The TODO file should have this structure:

```markdown
# Review Fixes: [Feature Name]

## Overview
Addressing incomplete implementation, review comments and CI/CD failures on PRs: {pr_numbers}

## Incomplete Implementation Items
[List any items from the design doc or original TODO that are missing or incomplete]

### Missing: [Brief description]
- **Status**: pending
- **From**: [Design doc / Original TODO stage X]
- **Target PR**: #[which PR should contain this]
- **Details**: [What specifically needs to be implemented]
- **Action required**: [What code changes are needed]

[... more missing items as needed ...]

## PR #[number]: [PR title]

### CI/CD Failures (if any)
- **Status**: pending
- **Check name**: [e.g., tests, lint, type-check]
- **Error summary**: [Brief description of what's failing]
- **Error details**:
  ```
  [Actual error output from the logs]
  ```
- **Files affected**: [file paths if identifiable]
- **Action required**: [What needs to be fixed]

### Comment 1: [Brief summary of the comment]
- **Status**: pending
- **Author**: [reviewer name]
- **File**: [file path and line number if applicable]
- **Comment**: [The actual review comment text]
- **Action required**: [What needs to be done to address this]

[... more comments as needed ...]

## PR #[next number]: [PR title]
[... CI failures and comments for this PR ...]

## Notes
[Any additional notes about dependencies between fixes or overall approach]
```

### Guidelines
- Check implementation completeness FIRST - missing functionality is highest priority
- Then check CI/CD status - failing tests/lint/type-checks are next priority
- Include specific error messages and stack traces from CI logs
- Only include UNRESOLVED review comments (skip resolved threads)
- Skip comments that contain [RESOLVED] or start with [CLAUDE]
- Group by PR, with incomplete items and CI failures listed before review comments
- Be specific about what action is needed for each item

### Output (CRITICAL - Valid JSON Required)
After creating the TODO file, output the following JSON block at the END of your response.
You MUST output valid, parseable JSON. All fields are required.

---JSON_OUTPUT---
{{
  "todo_file_created": "{todo_file_path}",
  "num_incomplete_items": <number of missing/incomplete implementation items>,
  "num_comments": <total number of unresolved comments across all PRs>,
  "num_ci_failures": <total number of failing CI checks across all PRs>,
  "error": null
}}
---END_JSON---

If you encounter an error, still output JSON:

---JSON_OUTPUT---
{{
  "todo_file_created": null,
  "num_incomplete_items": 0,
  "num_comments": 0,
  "num_ci_failures": 0,
  "error": "<description of what went wrong>"
}}
---END_JSON---

## Begin
Check implementation completeness, fetch PR comments, check CI status, and create the fix plan."""


FIX_PROMPT_TEMPLATE = """You are addressing review comments on PR #{pr_number}.

## IMPORTANT: You are working in a Git Worktree
- Worktree path: {worktree_path}
- Branch: {branch}
- PR Number: {pr_number}
- This is an isolated worktree, not the main repository
- All git operations are already scoped to this branch

## Design Document
Location: {design_doc_path}

{design_content}
{original_todo_section}
## Implementation Plan (TODO)
Location: {todo_file_path}

{todo_content}

## Your Task
Address all issues for PR #{pr_number}.
{self_healing_section}
**CRITICAL**: You MUST complete ALL steps below, even if there are 0 comments to address.
The fix process is not complete until:
1. Base branch is merged in (origin/main)
2. All merge conflicts are resolved
3. All CI/CD checks pass
4. All unresolved comments are addressed (if any)

### 1. Update Branch FIRST (ALWAYS REQUIRED - EVEN WITH 0 COMMENTS)
- You are already on branch '{branch}' in a worktree
- Fetch latest: git fetch origin
- Pull latest changes: git pull origin {branch}
- **ALWAYS merge origin/main**: git merge origin/main
- **IMMEDIATELY RESOLVE ALL MERGE CONFLICTS** if any occur
- After resolving, run bin/run_lint.sh and bin/run_type_check.sh to verify
- Commit and push merge resolution if needed
- **This step is MANDATORY even if there are no review comments**

### 2. Check CI/CD Status (HIGHEST PRIORITY)
- Use: gh pr checks {pr_number}
- NEVER wait for CI/CD. If checks are running or pending, assume they PASSED.
- If ANY checks are failing:
  - Get the run ID: gh run list --branch {branch} --limit 1
  - View failure logs: gh run view <run_id> --log-failed
  - Identify the EXACT errors (test failures, lint errors, type errors)
  - These MUST be fixed before anything else

### 3. Fix ALL CI/CD Failures
If CI is failing, you MUST fix it:
- Read the error messages carefully from the TODO file or fetch fresh logs
- Fix test failures by correcting the code or updating tests
- Fix lint errors by reformatting or fixing style issues
- Fix type errors by correcting type annotations or logic
- Run local checks to verify (e.g. lint, type check, test)
- Commit and push the fixes
- Verify CI passes before moving to review comments

### 4. Fetch PR Details and Comments
- Use gh CLI to get PR info, review threads (with resolution status), and general comments
- Use GraphQL API to check which review threads are resolved vs unresolved

### 5. Identify Unresolved Comments
Skip comments that:
- Are in a resolved thread (isResolved == true)
- Contain [RESOLVED] in the body
- Start with [CLAUDE] (already handled by you)

### 6. Address EVERY Unresolved Comment (if any exist)
You MUST reply to EVERY single unresolved comment. No exceptions.

For each comment:
- **Code change requests**: Make the fix, then reply confirming
- **Questions**: Answer based on your understanding
- **Suggestions you disagree with**: Explain your reasoning politely
- **Unclear comments**: Ask for clarification
- **Cursor Bugbot comments**: Address the issue or explain why not applicable

### 7. How to Reply
- Use gh CLI to reply to review comments and issue comments
- ALWAYS prefix replies with [CLAUDE] so reviewers know it's automated

### 8. Resolve Threads When Appropriate
Use the GitHub GraphQL API to resolve review threads after addressing them.

### 9. Run post-PR quality workflow (see Post-PR Code Quality Workflow section below)
{post_pr_workflow_section}
{quality_checks_section}
### 10. Commit and Push
- Commit with descriptive message
- Push to the branch

### 11. Verify CI/CD Status After Push
After pushing, verify CI/CD status:
- Use: gh pr checks {pr_number}
- NEVER wait for CI/CD. If checks are running or pending, assume they PASSED.
- If any checks are FAILING, fix them
{merge_conflict_section}
{strict_json_section}
## Output Format
After processing PR #{pr_number}, output the following JSON block at the END of your response.
If CI/CD is running or pending, treat it as passed and set `ci_status` to "passing".

---JSON_OUTPUT---
{{
  "pr_number": {pr_number},
  "base_branch_merged": <true if origin/main was merged successfully, false otherwise>,
  "merge_conflicts": "<none|resolved|unresolved>",
  "unresolved_before": <count of unresolved comments before processing>,
  "addressed": <count of comments addressed>,
  "ci_status": "<passing|failing>",
  "done": <true ONLY if all conditions below are met>,
  "error": null
}}
---END_JSON---

**IMPORTANT**: `done` can ONLY be true if ALL of the following are satisfied:
- Base branch (origin/main) has been merged into this branch
- There are NO unresolved merge conflicts
- There are ZERO unresolved comments (`unresolved_before` after your processing should be 0)
- CI status is "passing"

If you fail after 5 retry attempts, output:

---JSON_OUTPUT---
{{
  "pr_number": {pr_number},
  "base_branch_merged": false,
  "merge_conflicts": "unresolved",
  "unresolved_before": <count>,
  "addressed": 0,
  "ci_status": "failing",
  "done": false,
  "error": "<description of what went wrong after 5 attempts>"
}}
---END_JSON---

## Begin
Process PR #{pr_number} now."""


def render_fix_planning_prompt(
    design_doc_path: Path,
    design_content: str,
    original_todo_content: str | None,
    pr_numbers: list[int],
    todo_file_path: Path,
) -> str:
    """Render the fix planning prompt.

    Args:
        design_doc_path: Path to the design document
        design_content: Content of the design document
        original_todo_content: Content of the original implementation TODO (from implement phase)
        pr_numbers: List of PR numbers to process
        todo_file_path: Path where the TODO file should be created

    Returns:
        The rendered prompt string
    """
    pr_numbers_str = " ".join(str(n) for n in pr_numbers)
    original_todo_section = _render_original_todo_section(original_todo_content)
    return render_template(
        FIX_PLANNING_PROMPT_TEMPLATE,
        design_doc_path=design_doc_path,
        design_content=design_content,
        original_todo_section=original_todo_section,
        pr_numbers=pr_numbers_str,
        todo_file_path=todo_file_path,
    )


def _render_original_todo_section(original_todo_content: str | None) -> str:
    """Render the original implementation TODO section.

    Args:
        original_todo_content: Content of the original implementation TODO, or None

    Returns:
        The rendered section string, or empty string if no original todo
    """
    if not original_todo_content:
        return ""
    return f"""
## Original Implementation TODO (from implement phase)

{original_todo_content}
"""


def render_fix_prompt(
    pr_number: int,
    branch: str,
    worktree_path: Path,
    design_doc_path: Path,
    design_content: str,
    original_todo_content: str | None,
    todo_file_path: Path,
    todo_content: str,
) -> str:
    """Render the fix prompt for a specific PR.

    Args:
        pr_number: The PR number to fix
        branch: The branch name for this PR
        worktree_path: Path to the worktree
        design_doc_path: Path to the design document
        design_content: Content of the design document
        original_todo_content: Content of the original implementation TODO (from implement phase)
        todo_file_path: Path to the TODO file
        todo_content: Content of the TODO file

    Returns:
        The rendered prompt string
    """
    original_todo_section = _render_original_todo_section(original_todo_content)
    return render_template(
        FIX_PROMPT_TEMPLATE,
        pr_number=pr_number,
        branch=branch,
        worktree_path=worktree_path,
        design_doc_path=design_doc_path,
        design_content=design_content,
        original_todo_section=original_todo_section,
        todo_file_path=todo_file_path,
        todo_content=todo_content,
        merge_conflict_section=MERGE_CONFLICT_SECTION,
        post_pr_workflow_section=POST_PR_WORKFLOW_SECTION,
        quality_checks_section=QUALITY_CHECKS_SECTION,
        self_healing_section=SELF_HEALING_SECTION,
        strict_json_section=STRICT_JSON_SECTION,
    )
