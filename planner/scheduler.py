"""Deterministic study scheduler for Lakshya."""

import math
from datetime import datetime, timedelta
from typing import Any

from models import CalendarEvent, Plan, StudyBlock, StudyTask
from planner.exceptions import SchedulingImpossible
from planner.policies import SchedulingPolicy, validate_policy


def _ensure_tz_aware(dt: datetime, name: str) -> None:
    """Ensure datetime is timezone-aware."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{name} must be timezone-aware")


def _is_rest_time(dt: datetime, policy: SchedulingPolicy) -> bool:
    """Check if a specific datetime falls within the mandatory rest hours."""
    start_h = policy.mandatory_rest_start_hour
    end_h = policy.mandatory_rest_end_hour
    if start_h == end_h:
        return False
    hour = dt.hour
    if start_h > end_h:
        # Rest spans overnight (e.g. 22:00 to 07:00)
        return hour >= start_h or hour < end_h
    else:
        # Rest during same day (e.g. 01:00 to 06:00)
        return start_h <= hour < end_h


def _slot_overlaps_rest(
    start: datetime, end: datetime, policy: SchedulingPolicy
) -> bool:
    """Check if time slot [start, end] overlaps mandatory rest period."""
    start_h = policy.mandatory_rest_start_hour
    end_h = policy.mandatory_rest_end_hour
    if start_h == end_h:
        return False

    curr = start
    while curr < end:
        if _is_rest_time(curr, policy):
            return True
        curr += timedelta(minutes=1)
    return False


def _intervals_overlap(
    s1: datetime, e1: datetime, s2: datetime, e2: datetime
) -> bool:
    """Return True if open interval (s1, e1) overlaps with (s2, e2)."""
    return s1 < e2 and s2 < e1


def find_available_slots(
    *,
    window_start: datetime,
    window_end: datetime,
    existing_events: list[CalendarEvent],
    policy: SchedulingPolicy,
) -> list[tuple[datetime, datetime]]:
    """Find non-overlapping available study slots inside [window_start, window_end]."""
    validate_policy(policy)
    _ensure_tz_aware(window_start, "window_start")
    _ensure_tz_aware(window_end, "window_end")

    if window_end <= window_start:
        return []

    # Input immutability: sort copy of existing events
    sorted_events = sorted(existing_events, key=lambda e: (e.start, e.end, e.id))
    for evt in sorted_events:
        _ensure_tz_aware(evt.start, "evt.start")
        _ensure_tz_aware(evt.end, "evt.end")

    block_dur = timedelta(minutes=policy.study_block_minutes)
    slots: list[tuple[datetime, datetime]] = []

    curr = window_start
    while curr + block_dur <= window_end:
        slot_start = curr
        slot_end = curr + block_dur

        # Check rest overlap
        if _slot_overlaps_rest(slot_start, slot_end, policy):
            curr += timedelta(minutes=1)
            continue

        # Check existing calendar events overlap
        conflict = False
        for evt in sorted_events:
            if _intervals_overlap(slot_start, slot_end, evt.start, evt.end):
                conflict = True
                if evt.end > curr:
                    curr = evt.end
                break

        if conflict:
            continue

        # Valid slot found
        slots.append((slot_start, slot_end))
        curr = slot_end + timedelta(minutes=policy.break_minutes)

    return slots


def validate_plan(
    plan: Plan,
    *,
    existing_events: list[CalendarEvent],
    tasks: list[StudyTask],
    now: datetime,
    policy: SchedulingPolicy,
) -> None:
    """Independently verify all scheduling invariants of a Plan."""
    validate_policy(policy)
    _ensure_tz_aware(now, "now")

    task_map = {t.id: t for t in tasks}
    daily_minutes: dict[Any, int] = {}
    sorted_blocks = sorted(plan.blocks, key=lambda b: (b.start, b.end, b.id))

    for i, block in enumerate(sorted_blocks):
        _ensure_tz_aware(block.start, "block.start")
        _ensure_tz_aware(block.end, "block.end")

        # Invariant 1: No past scheduling
        if block.start < now:
            raise ValueError(
                f"Block {block.id} starts in the past relative to now"
            )

        # Invariant 2: Valid task reference
        if block.task_id not in task_map:
            raise ValueError(
                f"Block {block.id} references unknown task {block.task_id}"
            )

        task = task_map[block.task_id]

        # Invariant 3: No completed tasks scheduled
        if task.completed:
            raise ValueError(
                f"Block {block.id} is assigned to completed task {task.id}"
            )

        # Invariant 4: End before task deadline
        if block.end > task.deadline:
            raise ValueError(
                f"Block {block.id} ends at {block.end.isoformat()}, "
                f"past deadline {task.deadline.isoformat()}"
            )

        # Invariant 5: Valid block duration
        dur_minutes = (block.end - block.start).total_seconds() / 60.0
        if abs(dur_minutes - policy.study_block_minutes) > 1e-5:
            raise ValueError(
                f"Block {block.id} duration {dur_minutes} does not match "
                f"policy block size {policy.study_block_minutes}"
            )

        # Invariant 6: Mandatory rest window
        if _slot_overlaps_rest(block.start, block.end, policy):
            raise ValueError(
                f"Block {block.id} [{block.start.isoformat()} - "
                f"{block.end.isoformat()}] overlaps mandatory rest period"
            )

        # Invariant 7: Existing event conflicts
        for evt in existing_events:
            _ensure_tz_aware(evt.start, "evt.start")
            _ensure_tz_aware(evt.end, "evt.end")
            if _intervals_overlap(block.start, block.end, evt.start, evt.end):
                raise ValueError(
                    f"Block {block.id} overlaps existing calendar event {evt.id}"
                )

        # Invariant 8: Block overlaps among generated study blocks
        for j in range(i + 1, len(sorted_blocks)):
            other = sorted_blocks[j]
            if _intervals_overlap(block.start, block.end, other.start, other.end):
                raise ValueError(
                    f"Block {block.id} overlaps with block {other.id}"
                )

        # Invariant 9: Daily study cap
        b_date = block.start.date()
        daily_minutes[b_date] = daily_minutes.get(b_date, 0) + int(dur_minutes)
        if daily_minutes[b_date] > policy.max_daily_minutes:
            raise ValueError(
                f"Daily cap {policy.max_daily_minutes} exceeded on {b_date}: "
                f"{daily_minutes[b_date]} minutes"
            )


def schedule_tasks(
    *,
    tasks: list[StudyTask],
    existing_events: list[CalendarEvent],
    now: datetime,
    policy: SchedulingPolicy,
) -> Plan:
    """Schedule study tasks into non-overlapping study blocks."""
    validate_policy(policy)
    _ensure_tz_aware(now, "now")

    # Input immutability: filter and sort copy of tasks
    eligible_tasks = [t for t in tasks if not t.completed]
    for t in eligible_tasks:
        _ensure_tz_aware(t.deadline, "t.deadline")

    # Deterministic sorting by (deadline, id)
    sorted_tasks = sorted(eligible_tasks, key=lambda t: (t.deadline, t.id))

    if not tasks:
        return Plan(goal_id="empty", blocks=[])

    goal_id = tasks[0].goal_id

    # Deterministic sorting of existing events
    sorted_events = sorted(existing_events, key=lambda e: (e.start, e.end, e.id))
    for evt in sorted_events:
        _ensure_tz_aware(evt.start, "evt.start")
        _ensure_tz_aware(evt.end, "evt.end")

    busy_intervals: list[tuple[datetime, datetime]] = [
        (e.start, e.end) for e in sorted_events
    ]
    daily_minutes: dict[Any, int] = {}
    scheduled_blocks: list[StudyBlock] = []

    block_dur = timedelta(minutes=policy.study_block_minutes)

    for task in sorted_tasks:
        num_blocks = math.ceil(task.estimated_minutes / policy.study_block_minutes)

        for b in range(num_blocks):
            curr = now
            found_slot: tuple[datetime, datetime] | None = None

            while curr + block_dur <= task.deadline:
                slot_start = curr
                slot_end = curr + block_dur

                # Rule 1: Future only
                if slot_start < now:
                    curr = now
                    continue

                # Rule 2: Deadline check
                if slot_end > task.deadline:
                    break

                # Rule 6: Rest window check
                if _slot_overlaps_rest(slot_start, slot_end, policy):
                    curr += timedelta(minutes=1)
                    continue

                # Rule 3 & 4: Busy interval check
                has_conflict = False
                for b_start, b_end in busy_intervals:
                    if _intervals_overlap(slot_start, slot_end, b_start, b_end):
                        has_conflict = True
                        if b_end > curr:
                            curr = b_end
                        break

                if has_conflict:
                    continue

                # Rule 5: Daily cap check
                slot_date = slot_start.date()
                current_daily = daily_minutes.get(slot_date, 0)
                cap_reached = (
                    current_daily + policy.study_block_minutes
                    > policy.max_daily_minutes
                )
                if cap_reached:
                    # Daily cap reached for slot_date: jump to next day
                    next_day = datetime(
                        slot_date.year,
                        slot_date.month,
                        slot_date.day,
                        tzinfo=slot_start.tzinfo,
                    ) + timedelta(days=1)
                    curr = next_day
                    continue

                # Valid slot found!
                found_slot = (slot_start, slot_end)
                break

            if found_slot is None:
                raise SchedulingImpossible(
                    f"Cannot fit task '{task.title}' (ID: {task.id}) before "
                    f"deadline. Placed {b}/{num_blocks} required blocks."
                )

            s_start, s_end = found_slot
            block_id = f"block_{task.id}_{b + 1}"
            block = StudyBlock(
                id=block_id,
                task_id=task.id,
                start=s_start,
                end=s_end,
                title=task.title,
            )
            scheduled_blocks.append(block)

            # Register block + break as busy time
            break_dur = timedelta(minutes=policy.break_minutes)
            busy_intervals.append((s_start, s_end + break_dur))

            s_date = s_start.date()
            daily_minutes[s_date] = (
                daily_minutes.get(s_date, 0) + policy.study_block_minutes
            )

            # Advance search cursor past current block + break
            curr = s_end + timedelta(minutes=policy.break_minutes)

    scheduled_blocks.sort(key=lambda b: (b.start, b.end, b.id))
    plan = Plan(goal_id=goal_id, blocks=scheduled_blocks)

    # Independent plan validation
    validate_plan(
        plan,
        existing_events=existing_events,
        tasks=tasks,
        now=now,
        policy=policy,
    )
    return plan
