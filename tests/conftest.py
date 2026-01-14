"""Shared test fixtures for Smithers tests."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_todo_content() -> str:
    """Return sample TODO file content for testing."""
    return """# Implementation Plan: Test Feature

## Overview
Testing the TODO parser functionality.

## Stages

### Stage 1: Create Models
- **Status**: pending
- **Branch**: feature/models
- **Parallel group**: 1
- **Depends on**: none
- **PR**: (to be filled in)
- **Description**: Create the data models for the feature
- **Files to create/modify**:
  - [models/user.py]: Create User model
  - [models/settings.py]: Create Settings model
- **Acceptance criteria**:
  - [ ] User model has all required fields
  - [ ] Settings model validates correctly

### Stage 2: Create API
- **Status**: pending
- **Branch**: feature/api
- **Parallel group**: 1
- **Depends on**: none
- **PR**: (to be filled in)
- **Description**: Create API endpoints
- **Files to create/modify**:
  - [api/routes.py]: Add routes
- **Acceptance criteria**:
  - [ ] All endpoints return correct status codes

### Stage 3: Integration
- **Status**: pending
- **Branch**: feature/integration
- **Parallel group**: 2
- **Depends on**: Stage 1, Stage 2
- **PR**: (to be filled in)
- **Description**: Integrate models with API
- **Files to create/modify**:
  - [api/handlers.py]: Wire up handlers
- **Acceptance criteria**:
  - [ ] End-to-end tests pass

## Notes
This is a test implementation plan.
"""


@pytest.fixture
def sample_todo_file(tmp_path: Path, sample_todo_content: str) -> Path:
    """Create a sample TODO file and return its path."""
    todo_file = tmp_path / "test-todo.md"
    todo_file.write_text(sample_todo_content)
    return todo_file


@pytest.fixture
def sample_design_doc(tmp_path: Path) -> Path:
    """Create a sample design document and return its path."""
    design_doc = tmp_path / "design.md"
    design_doc.write_text("""# Test Feature Design

## Overview
This is a test design document.

## Requirements
- Feature A
- Feature B

## Implementation Details
Details here...
""")
    return design_doc
