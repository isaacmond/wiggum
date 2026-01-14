"""Implementation phase prompt templates."""

from pathlib import Path

from smithers.prompts.templates import (
    MERGE_CONFLICT_SECTION,
    QUALITY_CHECKS_SECTION,
    render_template,
)

IMPLEMENTATION_PROMPT_TEMPLATE = """You are implementing Stage {stage_number} of a design document.

## IMPORTANT: You are working in a Git Worktree
- Worktree path: {worktree_path}
- Branch: {branch}
- This is an isolated worktree, not the main repository
- All git operations are already scoped to this branch

## Design Document
Location: {design_doc_path}

{design_content}

## Implementation Plan (TODO)
Location: {todo_file_path}

{todo_content}

## Your Task
Implement **Stage {stage_number}** as specified in the TODO file above.

### Instructions

1. **Read the TODO file** to understand what Stage {stage_number} requires
2. **You are already on branch '{branch}'** in a worktree - no need to checkout
3. **Merge base to stay up to date**:
   - git fetch origin
   - git merge origin/{worktree_base}
   - **RESOLVE ALL MERGE CONFLICTS** (see Merge Conflict Resolution section below)
4. **Implement the changes** as specified in the TODO, offloading as much logic and coding as possible to Claude Code CLI
5. **Run quality checks** (MUST ALL PASS):
   - bin/run_lint.sh
   - bin/run_type_check.sh
   - bin/run_test.sh
6. **Self-review and cleanup (if available in your environment)**:
   - Run `/code-review:code-review` to review your diff and apply actionable feedback
   - Run `/de-slopify` to remove AI-generated slop from the branch before finalizing
7. **Commit and push** with clear messages
8. **Create the PR (stacked when sequential)**:
   - If this stage depends on a previous stage, open the PR into that prior stage's PR/branch (stacked PR), not main
   - If this stage is in a parallel group (no dependency), open the PR into '{worktree_base}'
   - Title should reflect the stage
   - Body should include:
     - What this stage implements
     - The branch/PR this stacks on (if applicable) with a clear link
     - The full stage list from the TODO (so reviewers see the big picture)
9. **Update the TODO file** (in the MAIN repository, not this worktree):
   - Set this stage's Status to: completed
   - Fill in the PR number
   - Check off completed acceptance criteria
{merge_conflict_section}
### If You Discover Issues
If the plan needs adjustment:
- Note what changed in your commit message
- The TODO file updates will be coordinated after all parallel stages complete

### Output
When Stage {stage_number} is complete, output the following JSON block at the END of your response:

---JSON_OUTPUT---
{{
  "stage_number": {stage_number},
  "complete": true,
  "pr_number": <pr_number>,
  "branch": "{branch}"
}}
---END_JSON---

## Begin
Implement Stage {stage_number} now."""


def render_implementation_prompt(
    stage_number: int,
    branch: str,
    worktree_path: Path,
    worktree_base: str,
    design_doc_path: Path,
    design_content: str,
    todo_file_path: Path,
    todo_content: str,
) -> str:
    """Render the implementation prompt for a stage.

    Args:
        stage_number: The stage number being implemented
        branch: The branch name for this stage
        worktree_path: Path to the worktree
        worktree_base: The base branch for merging
        design_doc_path: Path to the design document
        design_content: Content of the design document
        todo_file_path: Path to the TODO file
        todo_content: Content of the TODO file

    Returns:
        The rendered prompt string
    """
    return render_template(
        IMPLEMENTATION_PROMPT_TEMPLATE,
        stage_number=stage_number,
        branch=branch,
        worktree_path=worktree_path,
        worktree_base=worktree_base,
        design_doc_path=design_doc_path,
        design_content=design_content,
        todo_file_path=todo_file_path,
        todo_content=todo_content,
        merge_conflict_section=MERGE_CONFLICT_SECTION,
        quality_checks_section=QUALITY_CHECKS_SECTION,
    )
