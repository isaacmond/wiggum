"""Planning phase prompt templates."""

from pathlib import Path

from wiggum.prompts.templates import render_template

PLANNING_PROMPT_TEMPLATE = """You are planning the implementation of a design document.

## Design Document
Location: {design_doc_path}

{design_content}

## Your Task
Analyze this design document and create a detailed implementation plan. You will output this plan as a TODO file that will guide subsequent implementation stages.

### Create the TODO File
Create a file at: {todo_file_path}

The TODO file should have this structure:

```markdown
# Implementation Plan: [Feature Name]

## Overview
[Brief description of what we're implementing]

## Stages

### Stage 1: [Title]
- **Status**: pending
- **Branch**: [suggested branch name]
- **Parallel group**: [group_id - stages with same group_id run in parallel]
- **Depends on**: none (or Stage N)
- **PR**: (to be filled in)
- **Description**: [Detailed description of what this stage implements]
- **Files to create/modify**:
  - [file1.py]: [what to do]
  - [file2.py]: [what to do]
- **Acceptance criteria**:
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]

### Stage 2: [Title]
- **Status**: pending
- **Branch**: [suggested branch name]
- **Parallel group**: [group_id]
- **Depends on**: Stage 1
- **PR**: (to be filled in)
- **Description**: [Detailed description]
- **Files to create/modify**:
  - [file3.py]: [what to do]
- **Acceptance criteria**:
  - [ ] [Criterion 1]

[... more stages as needed ...]

## Notes
[Any additional notes, risks, or considerations]
```

### Guidelines
- Break the work into 2-6 logical stages
- Each stage should be a reviewable, self-contained PR
- Specify dependencies clearly (which stages must come before)
- Be specific about which files to create/modify
- Include clear acceptance criteria for each stage
- Consider: database migrations first, then models, then services, then handlers, then tests

### Parallel Groups
Stages are executed by parallel group. Assign the **Parallel group** field to control execution:
- Stages with the SAME group ID (e.g., "1", "2") run IN PARALLEL in separate git worktrees
- Stages with DIFFERENT group IDs run SEQUENTIALLY (group 1 completes before group 2 starts)
- Use "sequential" as the group ID for stages that MUST run alone (e.g., due to complex dependencies)
- Independent stages that don't touch the same files can share a group ID
- Stages that depend on each other MUST have different group IDs

Example:
- Stage 1 (models): Parallel group: 1
- Stage 2 (API endpoints): Parallel group: 1  (runs in parallel with Stage 1)
- Stage 3 (integration): Parallel group: 2    (waits for group 1 to complete)

### Output
After creating the TODO file, output:
TODO_FILE_CREATED: {todo_file_path}
NUM_STAGES: <number>
PARALLEL_GROUPS: <comma-separated list of unique group IDs in execution order>

## Begin
Analyze the design and create the implementation plan."""


def render_planning_prompt(
    design_doc_path: Path,
    design_content: str,
    todo_file_path: Path,
) -> str:
    """Render the planning prompt.

    Args:
        design_doc_path: Path to the design document
        design_content: Content of the design document
        todo_file_path: Path where the TODO file should be created

    Returns:
        The rendered prompt string
    """
    return render_template(
        PLANNING_PROMPT_TEMPLATE,
        design_doc_path=design_doc_path,
        design_content=design_content,
        todo_file_path=todo_file_path,
    )
