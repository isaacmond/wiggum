"""Standardize prompt templates for PR series standardization."""

from smithers.prompts.templates import (
    SELF_HEALING_SECTION,
    STRICT_JSON_SECTION,
    render_template,
)

STANDARDIZE_ANALYSIS_PROMPT_TEMPLATE = """You are analyzing a series of related pull requests to understand the overall feature being implemented and determine how to standardize their titles and descriptions.

## PR Diffs
Below are the diffs for each PR in the series. Analyze them to understand what feature is being implemented.

{pr_diffs}

## Your Task

1. **Identify the Feature**: Look at all the diffs together and determine what overall feature or capability is being implemented across these PRs.

2. **Determine Logical Order**: Based on dependencies and logical flow, determine the correct order of the PRs. Consider:
   - Which PRs introduce base models, types, or infrastructure
   - Which PRs build on changes from other PRs
   - Which PRs are final integration or cleanup steps

3. **Generate Summaries**: For each PR, create:
   - A concise title that describes what this specific PR does
   - A brief summary of the key changes
   - A list of key changes (bullet points)

4. **Create Standardized Titles**: Use this format:
   ```
   {{Feature Name}} ({{position}}/{{total}}): {{Description}}
   ```
   Example: `Candidate Search (2/8): Add filters to BaseSourcing class`
{self_healing_section}
{strict_json_section}
## Output Format
Output the following JSON block at the END of your response:

---JSON_OUTPUT---
{{
  "feature_name": "<name of the overall feature>",
  "total_prs": <number of PRs>,
  "prs": [
    {{
      "number": <PR number>,
      "position": <position in series, 1-indexed>,
      "suggested_title": "<Feature Name> (<position>/<total>): <Description>",
      "summary": "<1-2 sentence summary of this PR>",
      "key_changes": ["<change 1>", "<change 2>", "..."]
    }}
  ],
  "error": null
}}
---END_JSON---

If you encounter an error, output:

---JSON_OUTPUT---
{{
  "feature_name": null,
  "total_prs": 0,
  "prs": [],
  "error": "<description of what went wrong>"
}}
---END_JSON---

## Begin
Analyze the PR diffs and generate the standardization plan."""


STANDARDIZE_UPDATE_PROMPT_TEMPLATE = """You are updating a series of related pull requests with standardized titles and descriptions.

## Analysis Results
The following analysis was performed on the PR series:

Feature Name: {feature_name}
Total PRs: {total_prs}

{pr_analysis}

## PR Description Template
Use this template for each PR description:

```markdown
## Overview
{{brief_description}}

## Part of: {feature_name}
This is PR **{{position}}/{total_prs}** in a series implementing {feature_name}.

| # | PR | Title | Summary | Status |
|---|-----|-------|---------|--------|
{{pr_table_rows}}

## Changes in This PR
{{key_changes_list}}

## Dependencies
{{dependency_info}}
```

## Your Task

For each PR in the series, update its title and description using the GitHub CLI.

### Instructions

1. **Update Titles**: For each PR, run:
   ```bash
   gh pr edit <pr_number> --title "<new_title>"
   ```

2. **Update Descriptions**: For each PR, create the description using the template above and run:
   ```bash
   gh pr edit <pr_number> --body "<description>"
   ```

3. **Build the PR Table**: For each PR's description, include a table showing ALL PRs in the series:
   - Use the PR number with a link format: `#<number>`
   - Include the standardized title
   - Include the summary
   - Status should be "Open", "Merged", or "Closed" (fetch current status with `gh pr view <number> --json state`)

4. **Dependencies**: For each PR, note if it depends on a previous PR in the series:
   - If position > 1, note "Depends on PR #<previous_pr_number>"
   - If position == 1, write "None - this is the first PR in the series"
{self_healing_section}
{strict_json_section}
## Output Format
After updating all PRs, output the following JSON block at the END of your response:

---JSON_OUTPUT---
{{
  "updated_prs": [
    {{
      "number": <PR number>,
      "new_title": "<the new title>",
      "success": <true if both title and body were updated successfully>
    }}
  ],
  "error": null
}}
---END_JSON---

If you encounter an error, output:

---JSON_OUTPUT---
{{
  "updated_prs": [],
  "error": "<description of what went wrong>"
}}
---END_JSON---

## Begin
Update each PR's title and description now."""


def render_standardize_analysis_prompt(pr_diffs: list[dict[str, str | int]]) -> str:
    """Render the standardize analysis prompt with PR diffs.

    Args:
        pr_diffs: List of dicts with 'number', 'title', and 'diff' keys

    Returns:
        The rendered prompt string
    """
    diffs_text = ""
    for pr in pr_diffs:
        diffs_text += f"""
### PR #{pr['number']}: {pr['title']}

```diff
{pr['diff']}
```

"""
    return render_template(
        STANDARDIZE_ANALYSIS_PROMPT_TEMPLATE,
        pr_diffs=diffs_text.strip(),
        self_healing_section=SELF_HEALING_SECTION,
        strict_json_section=STRICT_JSON_SECTION,
    )


def render_standardize_update_prompt(
    feature_name: str,
    total_prs: int,
    prs: list[dict[str, str | int | list[str]]],
) -> str:
    """Render the standardize update prompt with analysis results.

    Args:
        feature_name: The identified feature name
        total_prs: Total number of PRs in the series
        prs: List of PR analysis results with 'number', 'position',
             'suggested_title', 'summary', and 'key_changes' keys

    Returns:
        The rendered prompt string
    """
    pr_analysis_text = ""
    for pr in prs:
        key_changes = pr.get("key_changes", [])
        if isinstance(key_changes, list):
            changes_text = "\n".join(f"  - {change}" for change in key_changes)
        else:
            changes_text = "  - (no changes listed)"

        pr_analysis_text += f"""
### PR #{pr['number']} (Position {pr['position']}/{total_prs})
- **Suggested Title**: {pr['suggested_title']}
- **Summary**: {pr['summary']}
- **Key Changes**:
{changes_text}

"""
    return render_template(
        STANDARDIZE_UPDATE_PROMPT_TEMPLATE,
        feature_name=feature_name,
        total_prs=total_prs,
        pr_analysis=pr_analysis_text.strip(),
        self_healing_section=SELF_HEALING_SECTION,
        strict_json_section=STRICT_JSON_SECTION,
    )
