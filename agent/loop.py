"""Agent loop logic for detecting missed study blocks and deterministic replanning."""

from datetime import datetime
from uuid import uuid4

from models import CalendarEvent, ReplanProposal, StudyBlock, StudyTask
from planner.policies import SchedulingPolicy
from planner.scheduler import schedule_tasks


def _ensure_tz_aware(dt: datetime, name: str) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{name} must be timezone-aware")


def detect_missed_blocks(
    calendar_events: list[CalendarEvent],
    now: datetime,
) -> list[CalendarEvent]:
    """Detect Lakshya-owned calendar events that ended before now."""
    _ensure_tz_aware(now, "now")

    missed: list[CalendarEvent] = []
    sorted_events = sorted(calendar_events, key=lambda e: (e.start, e.end, e.id))

    for evt in sorted_events:
        _ensure_tz_aware(evt.start, "evt.start")
        _ensure_tz_aware(evt.end, "evt.end")

        # Only Lakshya-owned events that ended before now and are not completed
        if evt.is_lakshya and evt.end < now and not evt.is_completed:
            missed.append(evt)

    return missed


def propose_replan(
    *,
    tasks: list[StudyTask],
    calendar_events: list[CalendarEvent],
    now: datetime,
    policy: SchedulingPolicy,
    reason: str = "Missed Lakshya study blocks detected",
    proposal_id: str | None = None,
) -> ReplanProposal:
    """Pure deterministic function proposing a study replan without side-effects."""
    _ensure_tz_aware(now, "now")

    missed_events = detect_missed_blocks(calendar_events, now)

    # Convert missed events into old_blocks
    old_blocks: list[StudyBlock] = []
    default_task_id = tasks[0].id if tasks else "task_unknown"

    for evt in missed_events:
        matching_tasks = [t for t in tasks if t.title in evt.title or t.id in evt.id]
        task_id = matching_tasks[0].id if matching_tasks else default_task_id

        old_blocks.append(
            StudyBlock(
                id=evt.id,
                task_id=task_id,
                start=evt.start,
                end=evt.end,
                title=evt.title,
            )
        )

    # Filter out missed past events from future busy events
    future_busy_events = [e for e in calendar_events if e not in missed_events]

    # Run deterministic scheduler
    plan = schedule_tasks(
        tasks=tasks,
        existing_events=future_busy_events,
        now=now,
        policy=policy,
    )

    pid = proposal_id or f"prop_{uuid4().hex[:8]}"

    return ReplanProposal(
        id=pid,
        reason=reason,
        old_blocks=old_blocks,
        new_blocks=plan.blocks,
        created_at=now,
        status="pending",
    )
