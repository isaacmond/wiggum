"""Implementation phase prompt templates."""

from pathlib import Path

from smithers.prompts.templates import (
    MERGE_CONFLICT_SECTION,
    POST_PR_WORKFLOW_SECTION,
    QUALITY_CHECKS_SECTION,
    SELF_HEALING_SECTION,
    STRICT_JSON_SECTION,
    TODO_STATE_SECTION,
    render_template,
)

IMPLEMENTATION_PROMPT_TEMPLATE = """You are implementing Stage {stage_number} of a design document.

## IMPORTANT: You are working in a Git Worktree
- Worktree path: {worktree_path}
- Branch: {branch}
- Session: {session_name}
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
{todo_state_section}
{self_healing_section}
### Instructions

1. **Update TODO status to in_progress** (see TODO State Management above)
2. **Read the TODO file** to understand what Stage {stage_number} requires
3. **You are already on branch '{branch}'** in a worktree - no need to checkout
4. **Merge base to stay up to date**:
   - git fetch origin
   - git merge origin/{worktree_base}
   - **RESOLVE ALL MERGE CONFLICTS** (see Merge Conflict Resolution section below)
5. **Implement the changes** as specified in the TODO
6. **Run quality checks** (MUST ALL PASS) (e.g. lint, type check, test)
7. **Commit and push** with clear messages
8. **Create the PR (stacked)**:
   - If this stage depends on a previous stage, open the PR into that prior stage's PR/branch (stacked PR), not main
   - If this is the first stage (no dependency), open the PR into '{worktree_base}'
   - Title should reflect the stage
   - Body should include:
     - What this stage implements
     - The branch/PR this stacks on (if applicable) with a clear link
     - The full stage list from the TODO (so reviewers see the big picture)
9. **Track the PR for cleanup**:
   - After creating the PR, append the PR number to the tracking file:
     `echo <pr_number> >> ~/.smithers/sessions/{session_name}/prs.txt`
   - This allows `smithers kill` to close PRs and delete branches if the session is killed
10. **Run post-PR quality workflow** (see Post-PR Code Quality Workflow section below)
11. **Update TODO status to completed** (see TODO State Management above)
{post_pr_workflow_section}
{merge_conflict_section}
### If You Discover Issues
If the plan needs adjustment:
- Note what changed in your commit message
- Update the TODO file with any relevant notes
{strict_json_section}
### Output
When Stage {stage_number} is complete, output the following JSON block at the END of your response:

---JSON_OUTPUT---
{{
  "stage_number": {stage_number},
  "complete": true,
  "pr_number": <pr_number or null if failed>,
  "branch": "{branch}",
  "error": null
}}
---END_JSON---

If you fail after 5 retry attempts, output:

---JSON_OUTPUT---
{{
  "stage_number": {stage_number},
  "complete": false,
  "pr_number": null,
  "branch": "{branch}",
  "error": "<description of what went wrong after 5 attempts>"
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
    session_name: str,
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
        session_name: The smithers session name for PR tracking

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
        session_name=session_name,
        merge_conflict_section=MERGE_CONFLICT_SECTION,
        post_pr_workflow_section=POST_PR_WORKFLOW_SECTION,
        quality_checks_section=QUALITY_CHECKS_SECTION,
        self_healing_section=SELF_HEALING_SECTION,
        strict_json_section=STRICT_JSON_SECTION,
        todo_state_section=TODO_STATE_SECTION,
    )
