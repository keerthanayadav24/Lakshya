"""Unit tests for Lakshya Pydantic domain models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models import CalendarEvent, StudyBlock, StudyGoal, StudyTask


def test_valid_study_goal() -> None:
    now = datetime.now(timezone.utc)
    goal = StudyGoal(
        id="goal-1",
        title="Calculus I Prep",
        syllabus_text="Derivatives and Integrals",
        deadline=now,
        created_at=now,
    )
    assert goal.id == "goal-1"
    assert goal.title == "Calculus I Prep"
    assert goal.syllabus_text == "Derivatives and Integrals"


def test_valid_study_task() -> None:
    now = datetime.now(timezone.utc)
    task = StudyTask(
        id="task-1",
        goal_id="goal-1",
        title="Read Chapter 3",
        estimated_minutes=45,
        deadline=now,
        completed=False,
    )
    assert task.id == "task-1"
    assert task.estimated_minutes == 45


def test_empty_id_rejection() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises((ValidationError, ValueError)):
        StudyGoal(
            id="",
            title="Calculus I Prep",
            syllabus_text="Derivatives",
            deadline=now,
            created_at=now,
        )

    with pytest.raises((ValidationError, ValueError)):
        StudyTask(
            id="   ",
            goal_id="goal-1",
            title="Read Chapter 3",
            estimated_minutes=45,
            deadline=now,
        )


def test_invalid_estimated_minutes_rejection() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises((ValidationError, ValueError)):
        StudyTask(
            id="task-1",
            goal_id="goal-1",
            title="Read Chapter 3",
            estimated_minutes=0,
            deadline=now,
        )

    with pytest.raises((ValidationError, ValueError)):
        StudyTask(
            id="task-1",
            goal_id="goal-1",
            title="Read Chapter 3",
            estimated_minutes=-15,
            deadline=now,
        )


def test_invalid_study_block_interval() -> None:
    earlier = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)  # end before start

    with pytest.raises((ValidationError, ValueError)):
        StudyBlock(
            id="block-1",
            task_id="task-1",
            start=earlier,
            end=later,
            title="Study Session",
        )


def test_unreasonable_study_block_duration() -> None:
    start = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)
    # 25 hours block
    end = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)

    with pytest.raises((ValidationError, ValueError)):
        StudyBlock(
            id="block-1",
            task_id="task-1",
            start=start,
            end=end,
            title="Marathon Study",
        )


def test_oversized_syllabus_rejection() -> None:
    now = datetime.now(timezone.utc)
    huge_syllabus = "A" * 50_001
    with pytest.raises((ValidationError, ValueError)):
        StudyGoal(
            id="goal-1",
            title="Calculus I Prep",
            syllabus_text=huge_syllabus,
            deadline=now,
            created_at=now,
        )


def test_timezone_aware_datetime_validation() -> None:
    naive_dt = datetime(2026, 10, 15, 12, 0)  # No tzinfo
    aware_dt = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    with pytest.raises((ValidationError, ValueError)):
        StudyGoal(
            id="goal-1",
            title="Physics Exam",
            syllabus_text="Kinematics",
            deadline=naive_dt,
            created_at=aware_dt,
        )

    with pytest.raises((ValidationError, ValueError)):
        CalendarEvent(
            id="event-1",
            start=naive_dt,
            end=aware_dt,
            title="Class",
        )
