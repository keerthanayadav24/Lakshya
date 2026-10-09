"""Unit tests for proposal database persistence and API endpoints."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.agent_routes import get_calendar_client
from config import settings
from db import (
    get_proposal,
    init_db,
    list_proposals,
    save_goal,
    save_proposal,
    save_task,
    update_proposal_status,
)
from main import app
from models import ReplanProposal, StudyBlock, StudyGoal, StudyTask
from tools.calendar import CalendarClient


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    db_f = str(tmp_path / "test_proposals.db")
    init_db(db_f)
    return db_f


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_proposal_persistence(tmp_db_path: str, base_now: datetime) -> None:
    old_b = StudyBlock(
        id="b1",
        task_id="t1",
        start=base_now,
        end=base_now + timedelta(hours=1),
        title="Old",
    )
    new_b = StudyBlock(
        id="b2",
        task_id="t1",
        start=base_now + timedelta(hours=2),
        end=base_now + timedelta(hours=3),
        title="New",
    )

    prop = ReplanProposal(
        id="p-100",
        reason="Test persistence",
        old_blocks=[old_b],
        new_blocks=[new_b],
        created_at=base_now,
        status="pending",
    )

    save_proposal(prop, db_path=tmp_db_path)
    loaded = get_proposal("p-100", db_path=tmp_db_path)

    assert loaded is not None
    assert loaded.id == "p-100"
    assert loaded.reason == "Test persistence"
    assert len(loaded.old_blocks) == 1
    assert loaded.old_blocks[0].id == "b1"
    assert len(loaded.new_blocks) == 1
    assert loaded.new_blocks[0].id == "b2"

    update_proposal_status("p-100", "applied", db_path=tmp_db_path)
    updated = get_proposal("p-100", db_path=tmp_db_path)
    assert updated is not None
    assert updated.status == "applied"


def test_list_proposals(tmp_db_path: str, base_now: datetime) -> None:
    p1 = ReplanProposal(
        id="p-1",
        reason="First",
        old_blocks=[],
        new_blocks=[],
        created_at=base_now,
        status="pending",
    )
    p2 = ReplanProposal(
        id="p-2",
        reason="Second",
        old_blocks=[],
        new_blocks=[],
        created_at=base_now.replace(hour=13),
        status="pending",
    )

    save_proposal(p1, db_path=tmp_db_path)
    save_proposal(p2, db_path=tmp_db_path)

    proposals = list_proposals(db_path=tmp_db_path)
    assert len(proposals) == 2
    # Ordered DESC by created_at
    assert proposals[0].id == "p-2"
    assert proposals[1].id == "p-1"


def test_api_proposal_endpoints(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")
    # Set up DB data for goal
    goal = StudyGoal(
        id="g-api",
        title="API Goal",
        syllabus_text="Syllabus",
        deadline=base_now.replace(day=20),
        created_at=base_now,
    )
    task = StudyTask(
        id="t-api",
        goal_id="g-api",
        title="API Task",
        estimated_minutes=50,
        deadline=base_now.replace(day=20),
    )
    save_goal(goal, db_path=tmp_db_path)
    save_task(task, db_path=tmp_db_path)

    # Mock CalendarClient dependency
    mock_service = MagicMock()
    mock_service.events().list().execute.return_value = {"items": []}
    mock_service.events().get().execute.return_value = {
        "id": "b1",
        "summary": "Old",
        "start": {"dateTime": base_now.isoformat()},
        "end": {"dateTime": base_now.replace(hour=13).isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    mock_service.events().insert().execute.return_value = {
        "id": "b2",
        "summary": "New",
        "start": {"dateTime": base_now.replace(hour=14).isoformat()},
        "end": {"dateTime": base_now.replace(hour=15).isoformat()},
        "extendedProperties": {"private": {"lakshya": "true"}},
    }
    fake_client = CalendarClient(mock_service)

    app.dependency_overrides[get_calendar_client] = lambda: fake_client
    client = TestClient(app)

    # 1. Create proposal (ZERO Calendar mutation)
    resp = client.post("/api/proposals?goal_id=g-api")
    assert resp.status_code == 201
    prop_data = resp.json()
    proposal_id = prop_data["id"]
    assert prop_data["status"] == "pending"

    # 2. Get proposals list
    resp_list = client.get("/api/proposals")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

    # 3. Approve with approved=false (Rejected by validation)
    resp_app_false = client.post(
        f"/api/proposals/{proposal_id}/approve",
        json={"approved": False},
    )
    assert resp_app_false.status_code == 400

    # 4. Approve with approved=true (Mutates Calendar)
    resp_app_true = client.post(
        f"/api/proposals/{proposal_id}/approve",
        json={"approved": True},
    )
    assert resp_app_true.status_code == 200
    assert resp_app_true.json()["status"] == "applied"

    # 5. Undo applied proposal
    resp_undo = client.post(f"/api/proposals/{proposal_id}/undo")
    assert resp_undo.status_code == 200
    assert resp_undo.json()["status"] == "undone"

    app.dependency_overrides.clear()


def test_malformed_proposal_json_handling(tmp_db_path: str, base_now: datetime) -> None:
    import sqlite3

    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO proposals (
                id, reason, old_blocks, new_blocks, created_at, status
            )
            VALUES ('p-corrupt', 'corrupt', '{INVALID_JSON', '[]', ?, 'pending')
            """,
            (base_now.isoformat(),),
        )
        conn.commit()

    with pytest.raises(ValueError, match="Malformed proposal data"):
        get_proposal("p-corrupt", db_path=tmp_db_path)


def test_concurrent_approval_protection(tmp_db_path: str, base_now: datetime) -> None:
    from db import atomic_update_proposal_status

    prop = ReplanProposal(
        id="p-race",
        reason="Race condition check",
        old_blocks=[],
        new_blocks=[],
        created_at=base_now,
        status="pending",
    )
    save_proposal(prop, db_path=tmp_db_path)

    # Simulating two concurrent requests: first request succeeds in transition
    res1 = atomic_update_proposal_status(
        "p-race", ["pending"], "applying", db_path=tmp_db_path
    )
    assert res1 is True

    # Second concurrent request fails because status is no longer 'pending'
    res2 = atomic_update_proposal_status(
        "p-race", ["pending"], "applying", db_path=tmp_db_path
    )
    assert res2 is False
