"""Property-based tests for Lakshya deterministic study scheduler using Hypothesis."""

from datetime import datetime, timedelta, timezone
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings

from models import CalendarEvent, StudyTask
from planner.exceptions import SchedulingImpossible
from planner.policies import SchedulingPolicy
from planner.scheduler import schedule_tasks

UTC = timezone.utc


@st.composite
def sample_task(draw: Any, base_now: datetime) -> StudyTask:
    idx = draw(st.integers(min_value=1, max_value=100))
    est = draw(st.integers(min_value=30, max_value=120))
    hours_ahead = draw(st.integers(min_value=12, max_value=72))
    deadline = base_now + timedelta(hours=hours_ahead)
    return StudyTask(
        id=f"task-{idx}",
        goal_id="goal-prop",
        title=f"Task {idx}",
        estimated_minutes=est,
        deadline=deadline,
        completed=False,
    )


@st.composite
def sample_event(draw: Any, base_now: datetime) -> CalendarEvent:
    idx = draw(st.integers(min_value=1, max_value=100))
    offset_hours = draw(st.integers(min_value=1, max_value=48))
    duration_mins = draw(st.integers(min_value=30, max_value=90))
    start = base_now + timedelta(hours=offset_hours)
    end = start + timedelta(minutes=duration_mins)
    return CalendarEvent(
        id=f"evt-{idx}",
        title=f"Event {idx}",
        start=start,
        end=end,
    )


@settings(max_examples=25)
@given(st.data())
def test_scheduler_properties_1_to_5(data: Any) -> None:
    base_now = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    policy = SchedulingPolicy(
        max_daily_minutes=240,
        study_block_minutes=50,
        break_minutes=10,
        mandatory_rest_start_hour=22,
        mandatory_rest_end_hour=7,
    )

    tasks = data.draw(
        st.lists(
            sample_task(base_now),
            min_size=1,
            max_size=3,
            unique_by=lambda t: t.id,
        )
    )
    events = data.draw(
        st.lists(
            sample_event(base_now),
            min_size=0,
            max_size=2,
            unique_by=lambda e: e.id,
        )
    )

    try:
        plan = schedule_tasks(
            tasks=tasks, existing_events=events, now=base_now, policy=policy
        )
    except SchedulingImpossible:
        return

    blocks = plan.blocks

    # PROPERTY 1: Generated study blocks never overlap one another
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            b1, b2 = blocks[i], blocks[j]
            assert not (b1.start < b2.end and b2.start < b1.end)

    # PROPERTY 2: Generated study blocks never overlap existing Calendar events
    for b in blocks:
        for e in events:
            assert not (b.start < e.end and e.start < b.end)

    # PROPERTY 3: Every generated block ends no later than its task deadline
    task_map = {t.id: t for t in tasks}
    for b in blocks:
        assert b.end <= task_map[b.task_id].deadline

    # PROPERTY 4: Daily generated study minutes never exceed max_daily_minutes
    daily_totals: dict[Any, int] = {}
    for b in blocks:
        d = b.start.date()
        daily_totals[d] = daily_totals.get(d, 0) + policy.study_block_minutes
        assert daily_totals[d] <= policy.max_daily_minutes

    # PROPERTY 5: No generated study block falls inside mandatory rest (22:00 to 07:00)
    for b in blocks:
        assert not (b.start.hour >= 22 or b.start.hour < 7)
        is_rest = (
            b.end.hour > 22
            or b.end.hour < 7
            or (b.end.hour == 22 and b.end.minute > 0)
        )
        assert not is_rest


@settings(max_examples=25)
@given(st.data())
def test_scheduler_properties_6_to_10(data: Any) -> None:
    base_now = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    policy = SchedulingPolicy()

    tasks = data.draw(
        st.lists(
            sample_task(base_now),
            min_size=1,
            max_size=3,
            unique_by=lambda t: t.id,
        )
    )
    events = data.draw(
        st.lists(
            sample_event(base_now),
            min_size=0,
            max_size=2,
            unique_by=lambda e: e.id,
        )
    )

    tasks_copy = [t.model_copy() for t in tasks]
    events_copy = [e.model_copy() for e in events]

    try:
        plan1 = schedule_tasks(
            tasks=tasks, existing_events=events, now=base_now, policy=policy
        )
    except SchedulingImpossible:
        return

    # PROPERTY 9 & 10: Scheduler does not mutate input lists or objects
    assert tasks == tasks_copy
    assert events == events_copy

    # PROPERTY 6: Identical inputs produce equivalent plans
    plan_identical = schedule_tasks(
        tasks=tasks, existing_events=events, now=base_now, policy=policy
    )
    assert plan1 == plan_identical

    # PROPERTY 7: Reordering input tasks does not change resulting plan
    reversed_tasks = list(reversed(tasks))
    plan_reordered_tasks = schedule_tasks(
        tasks=reversed_tasks, existing_events=events, now=base_now, policy=policy
    )
    assert plan1.blocks == plan_reordered_tasks.blocks

    # PROPERTY 8: Reordering existing Calendar events does not change resulting plan
    reversed_events = list(reversed(events))
    plan_reordered_events = schedule_tasks(
        tasks=tasks,
        existing_events=reversed_events,
        now=base_now,
        policy=policy,
    )
    assert plan1.blocks == plan_reordered_events.blocks
