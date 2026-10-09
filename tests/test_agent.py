"""Unit tests for Lakshya agent missed block detection and replan proposals."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.loop import detect_missed_blocks, propose_replan
from agent.service import (
    approve_proposal,
    create_replan_proposal,
    reject_proposal,
    undo_proposal,
)
from db import init_db, save_goal, save_task
from models import (
    CalendarEvent,
    ReplanProposal,
    StudyBlock,
    StudyGoal,
    StudyTask,
)
from planner.policies import SchedulingPolicy
from tools.calendar import CalendarClient, UnauthorizedCalendarMutation


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    db_f = str(tmp_path / "test_agent.db")
    init_db(db_f)
    return db_f


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_detect_missed_blocks(base_now: datetime) -> None:
    past_lakshya = CalendarEvent(
        id="l-past",
        title="Lakshya Math Session",
        start=base_now - timedelta(hours=3),
        end=base_now - timedelta(hours=2),
        is_lakshya=True,
    )
    future_lakshya = CalendarEvent(
        id="l-future",
        title="Lakshya Physics Session",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        is_lakshya=True,
    )
    past_user = CalendarEvent(
        id="u-past",
        title="User Doctor Appointment",
        start=base_now - timedelta(hours=3),
        end=base_now - timedelta(hours=2),
        is_lakshya=False,
    )

    events = [past_lakshya, future_lakshya, past_user]
    missed = detect_missed_blocks(events, base_now)

    assert len(missed) == 1
    assert missed[0].id == "l-past"
    # Verify input list is unchanged
    assert len(events) == 3


def test_propose_replan_zero_side_effects(base_now: datetime) -> None:
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Reading",
        estimated_minutes=50,
        deadline=base_now + timedelta(days=2),
    )
    past_lakshya = CalendarEvent(
        id="block_t1_1",
        title="Reading",
        start=base_now - timedelta(hours=3),
        end=base_now - timedelta(hours=2),
        is_lakshya=True,
    )
    events = [past_lakshya]
    policy = SchedulingPolicy()

    proposal = propose_replan(
        tasks=[task],
        calendar_events=events,
        now=base_now,
        policy=policy,
        reason="Test replan",
    )

    assert proposal.status == "pending"
    assert len(proposal.old_blocks) == 1
    assert len(proposal.new_blocks) >= 1
    assert proposal.new_blocks[0].start >= base_now


def test_create_replan_proposal_service(
    tmp_db_path: str, base_now: datetime
) -> None:
    # Set up DB data
    goal = StudyGoal(
        id="g1",
        title="Calculus",
        syllabus_text="Syllabus...",
        deadline=base_now + timedelta(days=3),
        created_at=base_now,
    )
    task = StudyTask(
        id="t1",
        goal_id="g1",
        title="Integration",
        estimated_minutes=50,
        deadline=base_now + timedelta(days=3),
    )
    save_goal(goal, db_path=tmp_db_path)
    save_task(task, db_path=tmp_db_path)

    # Mock calendar client
    mock_service = MagicMock()
    mock_service.events().list().execute.return_value = {
        "items": [
            {
                "id": "block_t1_1",
                "summary": "Integration",
                "start": {"dateTime": (base_now - timedelta(hours=3)).isoformat()},
                "end": {"dateTime": (base_now - timedelta(hours=2)).isoformat()},
                "extendedProperties": {"private": {"lakshya": "true"}},
            }
        ]
    }
    client = CalendarClient(mock_service)

    proposal = create_replan_proposal(
        goal_id="g1",
        calendar_client=client,
        now=base_now,
        db_path=tmp_db_path,
    )

    assert proposal.status == "pending"
    assert len(proposal.old_blocks) == 1
    # Verify ZERO calendar mutations occurred during proposal creation!
    mock_service.events().insert.assert_not_called()
    mock_service.events().update.assert_not_called()
    mock_service.events().delete.assert_not_called()


def test_approval_and_rejection_lifecycle(
    tmp_db_path: str, base_now: datetime
) -> None:
    # Create proposal in DB directly
    old_b = StudyBlock(
        id="b-old",
        task_id="t1",
        start=base_now - timedelta(hours=2),
        end=base_now - timedelta(hours=1),
        title="Old Block",
    )
    new_b = StudyBlock(
        id="b-new",
        task_id="t1",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        title="New Block",
    )
    proposal = ReplanProposal(
        id="prop-1",
        reason="Missed block",
        old_blocks=[old_b],
        new_blocks=[new_b],
        created_at=base_now,
        status="pending",
    )
    from db import save_proposal

    save_proposal(proposal, db_path=tmp_db_path)

    # Mock calendar client with Lakshya ownership
    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = {
        "id": "b-old",
        "summary": "Old Block",
        "start": {"dateTime": old_b.start.isoformat()},
        "end": {"dateTime": old_b.end.isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    mock_service.events().insert().execute.return_value = {
        "id": "b-new",
        "summary": "New Block",
        "start": {"dateTime": new_b.start.isoformat()},
        "end": {"dateTime": new_b.end.isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    client = CalendarClient(mock_service)

    # Approve proposal
    approved = approve_proposal("prop-1", client, db_path=tmp_db_path)
    assert approved.status == "applied"

    # Repeated approval fails
    with pytest.raises(ValueError, match="Cannot approve proposal"):
        approve_proposal("prop-1", client, db_path=tmp_db_path)

    # Undo applied proposal
    undone = undo_proposal("prop-1", client, db_path=tmp_db_path)
    assert undone.status == "undone"

    # Repeated undo fails
    with pytest.raises(ValueError, match="Cannot undo proposal"):
        undo_proposal("prop-1", client, db_path=tmp_db_path)


def test_reject_proposal(tmp_db_path: str, base_now: datetime) -> None:
    proposal = ReplanProposal(
        id="prop-reject",
        reason="Reason",
        old_blocks=[],
        new_blocks=[],
        created_at=base_now,
        status="pending",
    )
    from db import save_proposal

    save_proposal(proposal, db_path=tmp_db_path)

    rejected = reject_proposal("prop-reject", db_path=tmp_db_path)
    assert rejected.status == "rejected"

    with pytest.raises(ValueError, match="Cannot reject proposal"):
        reject_proposal("prop-reject", db_path=tmp_db_path)


def test_approval_unauthorized_user_event_rejection(
    tmp_db_path: str, base_now: datetime
) -> None:
    old_b = StudyBlock(
        id="user_event_1",
        task_id="t1",
        start=base_now - timedelta(hours=2),
        end=base_now - timedelta(hours=1),
        title="User Event",
    )
    proposal = ReplanProposal(
        id="prop-hack",
        reason="Reason",
        old_blocks=[old_b],
        new_blocks=[],
        created_at=base_now,
        status="pending",
    )
    from db import save_proposal

    save_proposal(proposal, db_path=tmp_db_path)

    # Mock calendar service returning non-Lakshya user event
    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = {
        "id": "user_event_1",
        "summary": "Doctor Appointment",
        "start": {"dateTime": old_b.start.isoformat()},
        "end": {"dateTime": old_b.end.isoformat()},
        # NOTE: NO lakshya ownership marker!
    }
    client = CalendarClient(mock_service)

    with pytest.raises(UnauthorizedCalendarMutation):
        approve_proposal("prop-hack", client, db_path=tmp_db_path)

    # Verify NO delete API call occurred
    mock_service.events().delete.assert_not_called()


def test_completed_block_not_detected(base_now: datetime) -> None:
    completed_event = CalendarEvent(
        id="c-past",
        title="Lakshya Math Session",
        start=base_now - timedelta(hours=3),
        end=base_now - timedelta(hours=2),
        is_lakshya=True,
        is_completed=True,
    )
    missed = detect_missed_blocks([completed_event], base_now)
    assert len(missed) == 0


def test_duplicate_or_conflicting_event_ids(
    tmp_db_path: str, base_now: datetime
) -> None:
    b1 = StudyBlock(
        id="dup-1",
        task_id="t1",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        title="Block 1",
    )
    b2 = StudyBlock(
        id="dup-1",  # Duplicate ID
        task_id="t1",
        start=base_now + timedelta(hours=3),
        end=base_now + timedelta(hours=4),
        title="Block 2",
    )
    prop = ReplanProposal(
        id="p-dup",
        reason="Dup check",
        old_blocks=[],
        new_blocks=[b1, b2],
        created_at=base_now,
        status="pending",
    )
    from db import save_proposal

    save_proposal(prop, db_path=tmp_db_path)

    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = None
    client = CalendarClient(mock_service)

    with pytest.raises(ValueError, match="Proposal contains duplicate"):
        approve_proposal("p-dup", client, db_path=tmp_db_path)


def test_user_event_substituted_for_new_block(
    tmp_db_path: str, base_now: datetime
) -> None:
    new_b = StudyBlock(
        id="clash-user-id",
        task_id="t1",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        title="New Block",
    )
    prop = ReplanProposal(
        id="p-clash",
        reason="Clash check",
        old_blocks=[],
        new_blocks=[new_b],
        created_at=base_now,
        status="pending",
    )
    from db import save_proposal

    save_proposal(prop, db_path=tmp_db_path)

    # Pre-verification sees non-Lakshya user event on calendar with same ID!
    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = {
        "id": "clash-user-id",
        "summary": "User Lunch",
        "start": {"dateTime": new_b.start.isoformat()},
        "end": {"dateTime": new_b.end.isoformat()},
        # NOT lakshya!
    }
    client = CalendarClient(mock_service)

    from tools.calendar import UnauthorizedCalendarMutation

    with pytest.raises(UnauthorizedCalendarMutation, match="Cannot overwrite"):
        approve_proposal("p-clash", client, db_path=tmp_db_path)

    # Zero mutations executed
    mock_service.events().insert().execute.assert_not_called()


def test_calendar_creation_fails_partway(
    tmp_db_path: str, base_now: datetime
) -> None:
    b1 = StudyBlock(
        id="nb-1",
        task_id="t1",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        title="New Block 1",
    )
    b2 = StudyBlock(
        id="nb-2",
        task_id="t1",
        start=base_now + timedelta(hours=3),
        end=base_now + timedelta(hours=4),
        title="New Block 2",
    )
    prop = ReplanProposal(
        id="p-fail-partway",
        reason="Fail check",
        old_blocks=[],
        new_blocks=[b1, b2],
        created_at=base_now,
        status="pending",
    )
    from db import get_proposal, save_proposal

    save_proposal(prop, db_path=tmp_db_path)

    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = None

    # First insert succeeds, second fails
    call_count = 0

    def mock_insert(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            m.execute.return_value = {
                "id": "nb-1",
                "summary": "New Block 1",
                "start": {"dateTime": b1.start.isoformat()},
                "end": {"dateTime": b1.end.isoformat()},
                "extendedProperties": {"private": {"lakshya": "true"}},
            }
        else:
            m.execute.side_effect = RuntimeError("Google API 500 Network Error")
        return m

    mock_service.events().insert.side_effect = mock_insert
    client = CalendarClient(mock_service)

    from tools.calendar import CalendarError

    with pytest.raises(CalendarError, match="Proposal application failed partway"):
        approve_proposal("p-fail-partway", client, db_path=tmp_db_path)

    # Verify proposal status is updated to partially_applied
    loaded = get_proposal("p-fail-partway", db_path=tmp_db_path)
    assert loaded is not None
    assert loaded.status == "partially_applied"


def test_undo_after_partial_application(
    tmp_db_path: str, base_now: datetime
) -> None:
    old_b = StudyBlock(
        id="ob-1",
        task_id="t1",
        start=base_now - timedelta(hours=2),
        end=base_now - timedelta(hours=1),
        title="Old Block 1",
    )
    new_b = StudyBlock(
        id="nb-1",
        task_id="t1",
        start=base_now + timedelta(hours=1),
        end=base_now + timedelta(hours=2),
        title="New Block 1",
    )
    prop = ReplanProposal(
        id="p-partial-undo",
        reason="Partial undo test",
        old_blocks=[old_b],
        new_blocks=[new_b],
        created_at=base_now,
        status="partially_applied",
    )
    from db import save_proposal

    save_proposal(prop, db_path=tmp_db_path)

    mock_service = MagicMock()
    mock_service.events().get().execute.return_value = {
        "id": "nb-1",
        "summary": "New Block 1",
        "start": {"dateTime": new_b.start.isoformat()},
        "end": {"dateTime": new_b.end.isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    mock_service.events().insert().execute.return_value = {
        "id": "ob-1",
        "summary": "Old Block 1",
        "start": {"dateTime": old_b.start.isoformat()},
        "end": {"dateTime": old_b.end.isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    client = CalendarClient(mock_service)

    undone = undo_proposal("p-partial-undo", client, db_path=tmp_db_path)
    assert undone.status == "undone"

