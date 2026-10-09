"""Unit tests for LLM Pydantic schemas."""

import pytest
from pydantic import ValidationError

from llm.schemas import LLMTask, LLMTaskBreakdown


def test_valid_llm_task() -> None:
    task = LLMTask(title="Study Chapter 1", estimated_minutes=60)
    assert task.title == "Study Chapter 1"
    assert task.estimated_minutes == 60


def test_empty_title_rejection() -> None:
    with pytest.raises(ValidationError):
        LLMTask(title="", estimated_minutes=30)
    with pytest.raises(ValidationError):
        LLMTask(title="   ", estimated_minutes=30)


def test_oversized_title_rejection() -> None:
    long_title = "A" * 201
    with pytest.raises(ValidationError):
        LLMTask(title=long_title, estimated_minutes=30)


def test_estimated_minutes_boundaries() -> None:
    # < 10 rejected
    with pytest.raises(ValidationError):
        LLMTask(title="Task", estimated_minutes=9)
    # > 480 rejected
    with pytest.raises(ValidationError):
        LLMTask(title="Task", estimated_minutes=481)

    # Valid boundaries
    t1 = LLMTask(title="Task", estimated_minutes=10)
    t2 = LLMTask(title="Task", estimated_minutes=480)
    assert t1.estimated_minutes == 10
    assert t2.estimated_minutes == 480


def test_valid_llm_task_breakdown() -> None:
    breakdown = LLMTaskBreakdown(
        tasks=[
            LLMTask(title="T1", estimated_minutes=30),
            LLMTask(title="T2", estimated_minutes=45),
        ]
    )
    assert len(breakdown.tasks) == 2


def test_empty_tasks_list_rejection() -> None:
    with pytest.raises(ValidationError):
        LLMTaskBreakdown(tasks=[])


def test_tasks_list_over_50_rejection() -> None:
    many_tasks = [
        LLMTask(title=f"T{i}", estimated_minutes=30) for i in range(51)
    ]
    with pytest.raises(ValidationError):
        LLMTaskBreakdown(tasks=many_tasks)


def test_extra_fields_rejection() -> None:
    with pytest.raises(ValidationError):
        LLMTask.model_validate(
            {"title": "Valid Title", "estimated_minutes": 30, "malicious_field": "hack"}
        )
