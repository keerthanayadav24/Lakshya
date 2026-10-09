"""Unit tests for syllabus breakdown service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from guards.output_validation import OutputValidationError
from llm.gemini import GeminiClient
from llm.task_breakdown import breakdown_syllabus


def test_successful_syllabus_breakdown() -> None:
    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.generate_json.return_value = (
        '{"tasks": ['
        '{"title": "Derivatives Concept", "estimated_minutes": 60},'
        '{"title": "Integrals Practice", "estimated_minutes": 90}'
        ']}'
    )

    deadline = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
    tasks = breakdown_syllabus(
        goal_id="goal_math_101",
        syllabus_text="Calculus topic list...",
        deadline=deadline,
        gemini_client=mock_gemini,
    )

    assert len(tasks) == 2
    assert tasks[0].id == "task_goal_math_101_1"
    assert tasks[0].goal_id == "goal_math_101"
    assert tasks[0].title == "Derivatives Concept"
    assert tasks[0].estimated_minutes == 60
    assert tasks[0].deadline == deadline
    assert tasks[0].completed is False

    assert tasks[1].id == "task_goal_math_101_2"
    assert tasks[1].title == "Integrals Practice"
    assert tasks[1].estimated_minutes == 90


def test_breakdown_raises_validation_error_on_bad_json() -> None:
    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.generate_json.return_value = "```json\n{bad_json}\n```"

    deadline = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
    with pytest.raises(OutputValidationError):
        breakdown_syllabus(
            goal_id="g1",
            syllabus_text="Physics...",
            deadline=deadline,
            gemini_client=mock_gemini,
        )


def test_breakdown_validates_inputs() -> None:
    mock_gemini = MagicMock(spec=GeminiClient)
    deadline_aware = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)
    deadline_naive = datetime(2026, 10, 20, 18, 0)

    # Empty goal_id
    with pytest.raises(ValueError, match="goal_id"):
        breakdown_syllabus(
            goal_id="",
            syllabus_text="Text",
            deadline=deadline_aware,
            gemini_client=mock_gemini,
        )

    # Empty syllabus_text
    with pytest.raises(ValueError, match="syllabus_text"):
        breakdown_syllabus(
            goal_id="g1",
            syllabus_text="",
            deadline=deadline_aware,
            gemini_client=mock_gemini,
        )

    # Oversized syllabus_text
    with pytest.raises(ValueError, match="syllabus_text"):
        breakdown_syllabus(
            goal_id="g1",
            syllabus_text="A" * 50_001,
            deadline=deadline_aware,
            gemini_client=mock_gemini,
        )

    # Naive deadline
    with pytest.raises(ValueError, match="deadline"):
        breakdown_syllabus(
            goal_id="g1",
            syllabus_text="Text",
            deadline=deadline_naive,
            gemini_client=mock_gemini,
        )
