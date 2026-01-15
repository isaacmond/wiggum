"""Planning phase prompt templates."""

from pathlib import Path

from smithers.prompts.templates import render_template

PLANNING_PROMPT_TEMPLATE = """You are planning the implementation of a design document.

## Design Document
Location: {design_doc_path}

{design_content}

## Your Task
Carefully analyze this design document and create a very detailed implementation plan. You will output this plan as a TODO file that will guide subsequent implementation stages.
{branch_prefix_instruction}
### Create the TODO File
Create a file at: {todo_file_path}

The TODO file should have this structure:

```markdown
# Implementation Plan: [Feature Name]

## Overview
[Detailed description of what we're implementing]

## Stages

### Stage 1: [Title]
- **Status**: pending
- **Branch**: {branch_example_1}
- **Depends on**: none (or the actual branch name of the dependency, e.g., {branch_example_1})
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
- **Branch**: {branch_example_2}
- **Depends on**: {branch_example_1} (use the actual branch name, NOT "Stage 1")
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

IMPORTANT: For the "Depends on" field, use the actual branch name (e.g., "{branch_example_1}"), NOT "Stage 1". Use "none" if there is no dependency.

### Guidelines

**PR Size and Scope:**
- Each stage should produce a substantial PR of **hundreds of lines** (200-500+ lines is ideal)
- Aim for **fewer, larger PRs** rather than many small ones — consolidate related work
- If a stage would be under 100 lines, combine it with an adjacent stage
- A typical implementation should have 2-5 stages total, not 8-10

**Stage Structure:**
- Break the work into logical stages that are executed SEQUENTIALLY (one at a time)
- Each stage should be a reviewable, self-contained PR with a clear purpose
- Specify dependencies clearly (which stages must come before)
- Be specific about which files to create/modify
- Include clear acceptance criteria for each stage
- Consider ordering: database migrations first, then models, then services, then handlers
- Stages will be implemented one at a time in order, with each PR stacking on the previous

**Testing (CRITICAL):**
- Tests MUST be included in the same stage as the code they test — NEVER create separate testing stages/PRs
- Each stage should include relevant unit tests, integration tests, or both alongside the implementation
- A stage is not complete without tests for the functionality it introduces
- Do NOT create "Stage N: Add Tests" — instead, include tests in each implementation stage

### Output (CRITICAL - Valid JSON Required)
After creating the TODO file, output the following JSON block at the END of your response.
You MUST output valid, parseable JSON. All fields are required.

---JSON_OUTPUT---
{{
  "todo_file_created": "{todo_file_path}",
  "num_stages": <number>,
  "stages": [
    {{"number": 1, "branch": "<branch-name>", "base": "<base-branch-or-none>"}},
    {{"number": 2, "branch": "<branch-name>", "base": "<dependency-branch-name>"}},
    {{"number": 3, "branch": "<branch-name>", "base": "<dependency-branch-name>"}}
  ],
  "error": null
}}
---END_JSON---

- "base" should be "main" (or the configured base branch) for stages with no dependency
- "base" should be the actual branch name for stages that depend on another stage

If you encounter an error, still output JSON:

---JSON_OUTPUT---
{{
  "todo_file_created": null,
  "num_stages": 0,
  "stages": [],
  "error": "<description of what went wrong>"
}}
---END_JSON---

## Begin
Analyze the design and create the implementation plan."""


def render_planning_prompt(
    design_doc_path: Path,
    design_content: str,
    todo_file_path: Path,
    branch_prefix: str,
) -> str:
    """Render the planning prompt.

    Args:
        design_doc_path: Path to the design document
        design_content: Content of the design document
        todo_file_path: Path where the TODO file should be created
        branch_prefix: Prefix for branch names (e.g., "username/")

    Returns:
        The rendered prompt string
    """
    branch_example_1 = f"{branch_prefix}stage-1-models"
    branch_example_2 = f"{branch_prefix}stage-2-api"
    branch_prefix_instruction = f"""
### Branch Naming Convention
**IMPORTANT**: All branch names MUST start with the prefix `{branch_prefix}`.
For example: `{branch_prefix}stage-1-models`, `{branch_prefix}stage-2-api`, etc.
"""

    return render_template(
        PLANNING_PROMPT_TEMPLATE,
        design_doc_path=design_doc_path,
        design_content=design_content,
        todo_file_path=todo_file_path,
        branch_prefix_instruction=branch_prefix_instruction,
        branch_example_1=branch_example_1,
        branch_example_2=branch_example_2,
    )
