"""Tests for prompt templates."""

from pathlib import Path

from smithers.prompts.fix import render_fix_planning_prompt, render_fix_prompt
from smithers.prompts.implementation import render_implementation_prompt
from smithers.prompts.planning import render_planning_prompt


class TestPlanningPrompt:
    """Tests for the planning prompt template."""

    def test_render_planning_prompt(self) -> None:
        """Test rendering the planning prompt."""
        prompt = render_planning_prompt(
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design\n\nThis is the design.",
            todo_file_path=Path("/path/to/todo.md"),
            branch_prefix="username/",
        )

        assert "/path/to/design.md" in prompt
        assert "# Design" in prompt
        assert "/path/to/todo.md" in prompt
        assert "---JSON_OUTPUT---" in prompt
        assert '"num_stages"' in prompt
        assert '"todo_file_created"' in prompt

    def test_prompt_contains_guidelines(self) -> None:
        """Test that the prompt contains necessary guidelines."""
        prompt = render_planning_prompt(
            design_doc_path=Path("design.md"),
            design_content="content",
            todo_file_path=Path("todo.md"),
            branch_prefix="feature/",
        )

        assert "SEQUENTIALLY" in prompt
        assert "Depends on" in prompt
        assert "Acceptance criteria" in prompt

    def test_render_planning_prompt_with_branch_prefix(self) -> None:
        """Test rendering the planning prompt with a branch prefix."""
        prompt = render_planning_prompt(
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design\n\nThis is the design.",
            todo_file_path=Path("/path/to/todo.md"),
            branch_prefix="username/",
        )

        # Should contain the prefix instruction
        assert "username/" in prompt
        assert "username/stage-1-models" in prompt
        assert "username/stage-2-api" in prompt
        assert "Branch Naming Convention" in prompt
        assert "MUST start with the prefix" in prompt


class TestImplementationPrompt:
    """Tests for the implementation prompt template."""

    def test_render_implementation_prompt(self) -> None:
        """Test rendering the implementation prompt."""
        prompt = render_implementation_prompt(
            stage_number=1,
            branch="feature/test",
            worktree_path=Path("/worktrees/feature-test"),
            worktree_base="main",
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            todo_file_path=Path("/path/to/todo.md"),
            todo_content="# TODO",
            session_name="smithers-impl-test",
        )

        assert "Stage 1" in prompt
        assert "feature/test" in prompt
        assert "/worktrees/feature-test" in prompt
        assert "---JSON_OUTPUT---" in prompt
        assert '"complete"' in prompt
        assert '"pr_number"' in prompt
        assert "code-simplifier subagent" in prompt
        assert "de-slopify skill" in prompt
        assert "code-review subagent" in prompt
        assert "smithers-impl-test" in prompt
        assert "prs.txt" in prompt

    def test_prompt_contains_quality_checks(self) -> None:
        """Test that the prompt includes quality check instructions."""
        prompt = render_implementation_prompt(
            stage_number=1,
            branch="test",
            worktree_path=Path("/test"),
            worktree_base="main",
            design_doc_path=Path("design.md"),
            design_content="",
            todo_file_path=Path("todo.md"),
            todo_content="",
            session_name="smithers-impl-test",
        )

        assert "quality checks" in prompt
        assert "lint" in prompt
        assert "type check" in prompt
        assert "test" in prompt

    def test_prompt_contains_merge_conflict_section(self) -> None:
        """Test that merge conflict resolution instructions are included."""
        prompt = render_implementation_prompt(
            stage_number=1,
            branch="test",
            worktree_path=Path("/test"),
            worktree_base="main",
            design_doc_path=Path("design.md"),
            design_content="",
            todo_file_path=Path("todo.md"),
            todo_content="",
            session_name="smithers-impl-test",
        )

        assert "Merge Conflict" in prompt
        assert "conflict markers" in prompt

    def test_prompt_mentions_pr_stacking(self) -> None:
        """Test that implementation prompt clarifies PR stacking."""
        prompt = render_implementation_prompt(
            stage_number=2,
            branch="feature/test",
            worktree_path=Path("/worktrees/feature-test"),
            worktree_base="main",
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            todo_file_path=Path("/path/to/todo.md"),
            todo_content="# TODO",
            session_name="smithers-impl-test",
        )

        assert "stacked" in prompt


class TestFixPrompts:
    """Tests for the fix prompt templates."""

    def test_render_fix_planning_prompt(self) -> None:
        """Test rendering the fix planning prompt."""
        prompt = render_fix_planning_prompt(
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            original_todo_content=None,
            pr_numbers=[123, 456],
            todo_file_path=Path("/path/to/todo.md"),
        )

        assert "123" in prompt
        assert "456" in prompt
        assert "CI/CD" in prompt
        assert "review comments" in prompt.lower()

    def test_render_fix_planning_prompt_with_original_todo(self) -> None:
        """Test rendering the fix planning prompt with original TODO."""
        prompt = render_fix_planning_prompt(
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            original_todo_content="# Original TODO\n- [ ] Step 1\n- [ ] Step 2",
            pr_numbers=[123],
            todo_file_path=Path("/path/to/todo.md"),
        )

        assert "Original Implementation TODO" in prompt
        assert "Step 1" in prompt
        assert "Step 2" in prompt

    def test_render_fix_prompt(self) -> None:
        """Test rendering the fix prompt for a specific PR."""
        prompt = render_fix_prompt(
            pr_number=123,
            branch="feature/test",
            worktree_path=Path("/worktrees/feature-test"),
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            original_todo_content=None,
            todo_file_path=Path("/path/to/todo.md"),
            todo_content="# TODO",
        )

        assert "PR #123" in prompt
        assert "feature/test" in prompt
        assert "---JSON_OUTPUT---" in prompt
        assert '"done"' in prompt
        assert '"ci_status"' in prompt
        assert "code-simplifier subagent" in prompt
        assert "de-slopify skill" in prompt
        assert "code-review subagent" in prompt

    def test_render_fix_prompt_with_original_todo(self) -> None:
        """Test rendering the fix prompt with original TODO."""
        prompt = render_fix_prompt(
            pr_number=123,
            branch="feature/test",
            worktree_path=Path("/worktrees/feature-test"),
            design_doc_path=Path("/path/to/design.md"),
            design_content="# Design",
            original_todo_content="# Original TODO\n- [ ] Implement feature X",
            todo_file_path=Path("/path/to/todo.md"),
            todo_content="# TODO",
        )

        assert "Original Implementation TODO" in prompt
        assert "Implement feature X" in prompt

    def test_fix_prompt_contains_claude_prefix_instruction(self) -> None:
        """Test that fix prompt instructs to prefix replies with [CLAUDE]."""
        prompt = render_fix_prompt(
            pr_number=1,
            branch="test",
            worktree_path=Path("/test"),
            design_doc_path=Path("design.md"),
            design_content="",
            original_todo_content=None,
            todo_file_path=Path("todo.md"),
            todo_content="",
        )

        assert "[CLAUDE]" in prompt

    def test_render_fix_planning_prompt_without_design_doc(self) -> None:
        """Test rendering the fix planning prompt without design doc."""
        prompt = render_fix_planning_prompt(
            design_doc_path=None,
            design_content=None,
            original_todo_content=None,
            pr_numbers=[123],
            todo_file_path=Path("/path/to/todo.md"),
        )

        # Should still contain the essential elements
        assert "123" in prompt
        assert "CI/CD" in prompt
        assert "review comments" in prompt.lower()
        # Should not contain design document section
        assert "## Design Document" not in prompt

    def test_render_fix_prompt_without_design_doc(self) -> None:
        """Test rendering the fix prompt without design doc."""
        prompt = render_fix_prompt(
            pr_number=123,
            branch="feature/test",
            worktree_path=Path("/worktrees/feature-test"),
            design_doc_path=None,
            design_content=None,
            original_todo_content=None,
            todo_file_path=Path("/path/to/todo.md"),
            todo_content="# TODO\n- Fix issue A",
        )

        # Should still contain the essential elements
        assert "PR #123" in prompt
        assert "feature/test" in prompt
        assert "---JSON_OUTPUT---" in prompt
        # Should not contain design document section
        assert "## Design Document" not in prompt
        # Should have skip message for design doc update step
        assert "skip this step" in prompt.lower()
