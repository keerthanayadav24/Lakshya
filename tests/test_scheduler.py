"""Unit tests for Lakshya deterministic study scheduler."""

from datetime import datetime, timedelta, timezone

import pytest

from models import CalendarEvent, StudyTask
from planner.exceptions import SchedulingImpossible
from planner.policies import SchedulingPolicy
from planner.scheduler import find_available_slots, schedule_tasks


@pytest.fixture
def default_policy() -> SchedulingPolicy:
    return SchedulingPolicy(
        max_daily_minutes=240,
        study_block_minutes=50,
        break_minutes=10,
        mandatory_rest_start_hour=22,
        mandatory_rest_end_hour=7,
    )


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)


def test_one_task_one_available_slot(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    deadline = base_now + timedelta(hours=3)
    task = StudyTask(
        id="task-1",
        goal_id="goal-1",
        title="Math Prep",
        estimated_minutes=50,
        deadline=deadline,
    )
    plan = schedule_tasks(
        tasks=[task],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )
    assert len(plan.blocks) == 1
    assert plan.blocks[0].task_id == "task-1"
    assert plan.blocks[0].start >= base_now
    assert plan.blocks[0].end <= deadline


def test_multiple_tasks_ordered_by_deadline(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    d1 = base_now + timedelta(hours=5)
    d2 = base_now + timedelta(hours=2)  # Earlier deadline!

    task_late = StudyTask(
        id="t-late",
        goal_id="g1",
        title="Late Task",
        estimated_minutes=50,
        deadline=d1,
    )
    task_early = StudyTask(
        id="t-early",
        goal_id="g1",
        title="Early Task",
        estimated_minutes=50,
        deadline=d2,
    )

    # Input list has late task first
    plan = schedule_tasks(
        tasks=[task_late, task_early],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )

    assert len(plan.blocks) == 2
    # The earlier deadline task must be scheduled first
    assert plan.blocks[0].task_id == "t-early"
    assert plan.blocks[1].task_id == "t-late"


def test_existing_busy_calendar_event(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    # Existing event 08:00 to 10:00
    evt = CalendarEvent(
        id="busy-1",
        title="Meeting",
        start=base_now,
        end=base_now + timedelta(hours=2),
    )
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Study",
        estimated_minutes=50,
        deadline=base_now + timedelta(hours=5),
    )

    plan = schedule_tasks(
        tasks=[task],
        existing_events=[evt],
        now=base_now,
        policy=default_policy,
    )

    assert len(plan.blocks) == 1
    # Must start at or after event end (10:00)
    assert plan.blocks[0].start >= evt.end


def test_exact_boundary_before_and_after_event(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    # Event from 09:00 to 10:00
    evt_start = base_now + timedelta(hours=1)
    evt_end = base_now + timedelta(hours=2)
    evt = CalendarEvent(id="e1", title="Class", start=evt_start, end=evt_end)

    # Block 1: 08:00 to 08:50 (ends before 09:00)
    task1 = StudyTask(
        id="t1",
        goal_id="g1",
        title="T1",
        estimated_minutes=50,
        deadline=base_now + timedelta(hours=5),
    )
    plan = schedule_tasks(
        tasks=[task1],
        existing_events=[evt],
        now=base_now,
        policy=default_policy,
    )

    assert len(plan.blocks) == 1
    assert plan.blocks[0].start == base_now
    assert plan.blocks[0].end == base_now + timedelta(minutes=50)


def test_daily_study_cap(base_now: datetime) -> None:
    policy = SchedulingPolicy(
        max_daily_minutes=100,  # Only 2 blocks of 50m per day
        study_block_minutes=50,
        break_minutes=10,
        mandatory_rest_start_hour=22,
        mandatory_rest_end_hour=7,
    )
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Big Task",
        estimated_minutes=150,  # Needs 3 blocks
        deadline=base_now + timedelta(days=2),
    )

    plan = schedule_tasks(
        tasks=[task],
        existing_events=[],
        now=base_now,
        policy=policy,
    )

    assert len(plan.blocks) == 3
    # Day 1 gets 2 blocks (100 mins max)
    day1_blocks = [b for b in plan.blocks if b.start.date() == base_now.date()]
    assert len(day1_blocks) == 2

    # Day 2 gets the 3rd block
    day2_blocks = [b for b in plan.blocks if b.start.date() > base_now.date()]
    assert len(day2_blocks) == 1


def test_mandatory_overnight_rest(base_now: datetime) -> None:
    policy = SchedulingPolicy(
        max_daily_minutes=500,
        study_block_minutes=50,
        break_minutes=10,
        mandatory_rest_start_hour=22,
        mandatory_rest_end_hour=7,
    )
    # Start at 21:30
    night_now = datetime(2026, 10, 15, 21, 30, tzinfo=timezone.utc)
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Late Study",
        estimated_minutes=50,
        deadline=night_now + timedelta(hours=15),
    )

    plan = schedule_tasks(
        tasks=[task],
        existing_events=[],
        now=night_now,
        policy=policy,
    )

    assert len(plan.blocks) == 1
    assert plan.blocks[0].start.hour >= 7
    assert plan.blocks[0].start.date() > night_now.date()


def test_task_deadline_enforcement(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    tight_deadline = base_now + timedelta(minutes=40)
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Impossible Task",
        estimated_minutes=50,
        deadline=tight_deadline,
    )

    with pytest.raises(SchedulingImpossible, match="Cannot fit task"):
        schedule_tasks(
            tasks=[task],
            existing_events=[],
            now=base_now,
            policy=default_policy,
        )


def test_task_requiring_multiple_blocks(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Long Reading",
        estimated_minutes=120,  # Requires ceil(120/50) = 3 blocks
        deadline=base_now + timedelta(hours=10),
    )

    plan = schedule_tasks(
        tasks=[task],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )

    assert len(plan.blocks) == 3
    b_dur = timedelta(minutes=default_policy.break_minutes)
    assert plan.blocks[1].start == plan.blocks[0].end + b_dur
    assert plan.blocks[2].start == plan.blocks[1].end + b_dur


def test_deterministic_repeated_scheduling(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    d1 = base_now + timedelta(hours=5)
    d2 = base_now + timedelta(hours=6)
    task1 = StudyTask(
        id="t1", goal_id="g1", title="T1", estimated_minutes=50, deadline=d1
    )
    task2 = StudyTask(
        id="t2", goal_id="g1", title="T2", estimated_minutes=100, deadline=d2
    )

    p1 = schedule_tasks(
        tasks=[task1, task2],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )
    p2 = schedule_tasks(
        tasks=[task1, task2],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )

    assert p1 == p2


def test_input_ordering_independence(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    d1 = base_now + timedelta(hours=4)
    d2 = base_now + timedelta(hours=8)
    task1 = StudyTask(
        id="t1", goal_id="g1", title="T1", estimated_minutes=50, deadline=d1
    )
    task2 = StudyTask(
        id="t2", goal_id="g1", title="T2", estimated_minutes=50, deadline=d2
    )

    p1 = schedule_tasks(
        tasks=[task1, task2],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )
    p2 = schedule_tasks(
        tasks=[task2, task1],
        existing_events=[],
        now=base_now,
        policy=default_policy,
    )

    assert p1.blocks == p2.blocks


def test_existing_lakshya_events_treated_as_busy(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    lakshya_evt = CalendarEvent(
        id="l-1",
        title="Existing Lakshya Session",
        start=base_now,
        end=base_now + timedelta(hours=1),
        is_lakshya=True,
    )
    d1 = base_now + timedelta(hours=5)
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="New Task",
        estimated_minutes=50,
        deadline=d1,
    )

    plan = schedule_tasks(
        tasks=[task],
        existing_events=[lakshya_evt],
        now=base_now,
        policy=default_policy,
    )

    assert len(plan.blocks) == 1
    assert plan.blocks[0].start >= lakshya_evt.end


def test_completed_tasks_ignored(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    task = StudyTask(
        id="t-done",
        goal_id="g1",
        title="Finished Task",
        estimated_minutes=50,
        deadline=base_now + timedelta(hours=5),
        completed=True,
    )
    plan = schedule_tasks(
        tasks=[task], existing_events=[], now=base_now, policy=default_policy
    )
    assert len(plan.blocks) == 0


def test_find_available_slots(
    default_policy: SchedulingPolicy, base_now: datetime
) -> None:
    w_start = base_now
    w_end = base_now + timedelta(hours=3)
    evt = CalendarEvent(
        id="e1",
        title="Busy",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
    )

    slots = find_available_slots(
        window_start=w_start,
        window_end=w_end,
        existing_events=[evt],
        policy=default_policy,
    )
    assert len(slots) >= 1
    for s_start, s_end in slots:
        assert not (s_start < evt.end and evt.start < s_end)
