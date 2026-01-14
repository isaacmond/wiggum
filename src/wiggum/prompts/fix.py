"""Fix phase prompt templates for PR review comments and CI failures."""

from pathlib import Path

from wiggum.prompts.templates import (
    MERGE_CONFLICT_SECTION,
    QUALITY_CHECKS_SECTION,
    render_template,
)

FIX_PLANNING_PROMPT_TEMPLATE = """You are creating a fix plan to address review comments AND CI/CD failures on pull requests.

## Design Document (for context)
Location: {design_doc_path}

{design_content}

## PRs to Process
{pr_numbers}

## Your Task
1. First, fetch the unresolved review comments from each PR using the GitHub CLI:
   - gh pr view <pr_number> --json reviewThreads,comments
   - Use GraphQL to get detailed thread info including resolution status

2. Check CI/CD status for each PR:
   - gh pr checks <pr_number>
   - If any checks are failing, get the failure details:
     - gh run list --branch <branch_name> --limit 1
     - gh run view <run_id> --log-failed
   - Extract the specific test failures, lint errors, or type check errors

3. Create a TODO file at: {todo_file_path}

The TODO file should have this structure:

```markdown
# Review Fixes: [Feature Name]

## Overview
Addressing review comments and CI/CD failures on PRs: {pr_numbers}

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

### Comment 2: [Brief summary]
- **Status**: pending
- **Author**: [reviewer name]
- **File**: [file path]
- **Comment**: [comment text]
- **Action required**: [action to take]

[... more comments as needed ...]

## PR #[next number]: [PR title]
[... CI failures and comments for this PR ...]

## Notes
[Any additional notes about dependencies between fixes or overall approach]
```

### Guidelines
- ALWAYS check CI/CD status first - failing tests/lint/type-checks are highest priority
- Include specific error messages and stack traces from CI logs
- Only include UNRESOLVED review comments (skip resolved threads)
- Skip comments that contain [RESOLVED] or start with [CLAUDE]
- Group by PR, with CI failures listed before review comments
- Be specific about what action is needed for each item

### Output
After creating the TODO file, output:
TODO_FILE_CREATED: {todo_file_path}
NUM_COMMENTS: <total number of unresolved comments across all PRs>
NUM_CI_FAILURES: <total number of failing CI checks across all PRs>

## Begin
Fetch the PR comments, check CI status, and create the fix plan."""


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

## Implementation Plan (TODO)
Location: {todo_file_path}

{todo_content}

## Your Task
Address all issues for PR #{pr_number}:

### 1. Check CI/CD Status FIRST (HIGHEST PRIORITY)
- Use: gh pr checks {pr_number}
- If ANY checks are failing:
  - Get the run ID: gh run list --branch {branch} --limit 1
  - View failure logs: gh run view <run_id> --log-failed
  - Identify the EXACT errors (test failures, lint errors, type errors)
  - These MUST be fixed before anything else

### 2. Fetch PR Details and Comments
- Use gh CLI to get PR info, review threads (with resolution status), and general comments
- Use GraphQL API to check which review threads are resolved vs unresolved

### 3. Identify Unresolved Comments
Skip comments that:
- Are in a resolved thread (isResolved == true)
- Contain [RESOLVED] in the body
- Start with [CLAUDE] (already handled by you)

### 4. Update Branch (MERGE CONFLICTS ARE BLOCKING)
- You are already on branch '{branch}' in a worktree
- Pull latest changes: git pull origin {branch}
- Merge origin/main to stay up to date: git merge origin/main
- **IMMEDIATELY RESOLVE ALL MERGE CONFLICTS** before proceeding
- After resolving, run bin/run_lint.sh and bin/run_type_check.sh to verify

### 5. Fix ALL CI/CD Failures (before addressing comments)
If CI is failing, you MUST fix it first:
- Read the error messages carefully from the TODO file or fetch fresh logs
- Fix test failures by correcting the code or updating tests
- Fix lint errors by reformatting or fixing style issues
- Fix type errors by correcting type annotations or logic
- Run local checks to verify: bin/run_lint.sh, bin/run_type_check.sh, bin/run_test.sh
- Commit and push the fixes
- Verify CI passes before moving to review comments

### 6. Address EVERY Unresolved Comment
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
{quality_checks_section}
### 10. Commit and Push
- Commit with descriptive message
- Push to the branch

### 11. Verify CI/CD Status After Push
After pushing, verify CI/CD status:
- Use: gh pr checks {pr_number}
- If any checks are FAILING, fix them
{merge_conflict_section}
## Output Format
After processing PR #{pr_number}, output:
PR_{pr_number}_MERGE_CONFLICTS: <none|resolved>
PR_{pr_number}_UNRESOLVED_BEFORE: <count>
PR_{pr_number}_ADDRESSED: <count>
PR_{pr_number}_CI_STATUS: <passing|failing|pending>

If NO unresolved comments AND CI passing:
PR_{pr_number}_DONE: true

## Begin
Process PR #{pr_number} now."""


def render_fix_planning_prompt(
    design_doc_path: Path,
    design_content: str,
    pr_numbers: list[int],
    todo_file_path: Path,
) -> str:
    """Render the fix planning prompt.

    Args:
        design_doc_path: Path to the design document
        design_content: Content of the design document
        pr_numbers: List of PR numbers to process
        todo_file_path: Path where the TODO file should be created

    Returns:
        The rendered prompt string
    """
    pr_numbers_str = " ".join(str(n) for n in pr_numbers)
    return render_template(
        FIX_PLANNING_PROMPT_TEMPLATE,
        design_doc_path=design_doc_path,
        design_content=design_content,
        pr_numbers=pr_numbers_str,
        todo_file_path=todo_file_path,
    )


def render_fix_prompt(
    pr_number: int,
    branch: str,
    worktree_path: Path,
    design_doc_path: Path,
    design_content: str,
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
        todo_file_path: Path to the TODO file
        todo_content: Content of the TODO file

    Returns:
        The rendered prompt string
    """
    return render_template(
        FIX_PROMPT_TEMPLATE,
        pr_number=pr_number,
        branch=branch,
        worktree_path=worktree_path,
        design_doc_path=design_doc_path,
        design_content=design_content,
        todo_file_path=todo_file_path,
        todo_content=todo_content,
        quality_checks_section=QUALITY_CHECKS_SECTION,
        merge_conflict_section=MERGE_CONFLICT_SECTION,
    )
