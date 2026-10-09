"""Unit tests for strict LLM output validation guard."""

import pytest

from guards.output_validation import OutputValidationError, parse_task_breakdown


def test_valid_json_parsing() -> None:
    raw_json = '{"tasks": [{"title": "Read Chapter 1", "estimated_minutes": 45}]}'
    result = parse_task_breakdown(raw_json)
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "Read Chapter 1"
    assert result.tasks[0].estimated_minutes == 45


def test_markdown_code_fences_rejection() -> None:
    fenced_json = """```json
    {"tasks": [{"title": "Read Chapter 1", "estimated_minutes": 45}]}
    ```"""
    with pytest.raises(OutputValidationError, match="markdown code fences"):
        parse_task_breakdown(fenced_json)


def test_malformed_json_rejection() -> None:
    bad_json = '{"tasks": [{"title": "Read Chapter 1", "estimated_minutes":}'
    with pytest.raises(OutputValidationError, match="Invalid JSON string"):
        parse_task_breakdown(bad_json)


def test_non_dict_json_rejection() -> None:
    list_json = '[{"title": "Read Chapter 1", "estimated_minutes": 45}]'
    with pytest.raises(OutputValidationError, match="must be a top-level JSON object"):
        parse_task_breakdown(list_json)


def test_invalid_schema_rejection() -> None:
    missing_minutes = '{"tasks": [{"title": "Read Chapter 1"}]}'
    with pytest.raises(OutputValidationError, match="schema validation failed"):
        parse_task_breakdown(missing_minutes)


def test_extra_fields_rejection() -> None:
    extra_fields = (
        '{"tasks": [{"title": "Task", "estimated_minutes": 30}], "extra": "unwanted"}'
    )
    with pytest.raises(OutputValidationError, match="schema validation failed"):
        parse_task_breakdown(extra_fields)


def test_empty_string_rejection() -> None:
    with pytest.raises(OutputValidationError, match="empty"):
        parse_task_breakdown("  ")
