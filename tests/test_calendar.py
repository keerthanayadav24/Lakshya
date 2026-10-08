"""Unit tests for Google Calendar client and ownership guards."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from models import StudyBlock
from tools.calendar import (
    CalendarClient,
    CalendarError,
    UnauthorizedCalendarMutation,
)


class FakeCalendarService:
    """In-memory fake Google Calendar API service for testing."""

    def __init__(self) -> None:
        self.events_db: dict[str, dict[str, Any]] = {}
        self.list_call_count = 0
        self.get_call_count = 0
        self.insert_call_count = 0
        self.update_call_count = 0
        self.delete_call_count = 0

    def events(self) -> Any:
        service = self

        class EventsResource:
            def list(self, **kwargs: Any) -> Any:
                service.list_call_count += 1
                mock_req = MagicMock()
                items = list(service.events_db.values())
                mock_req.execute.return_value = {"items": items}
                return mock_req

            def get(self, calendarId: str, eventId: str) -> Any:
                service.get_call_count += 1
                mock_req = MagicMock()
                if eventId not in service.events_db:
                    mock_req.execute.side_effect = Exception("404 Not Found")
                else:
                    mock_req.execute.return_value = service.events_db[eventId]
                return mock_req

            def insert(self, calendarId: str, body: dict[str, Any]) -> Any:
                service.insert_call_count += 1
                mock_req = MagicMock()
                new_id = f"event_{len(service.events_db) + 1}"
                item = dict(body)
                item["id"] = new_id
                service.events_db[new_id] = item
                mock_req.execute.return_value = item
                return mock_req

            def update(
                self, calendarId: str, eventId: str, body: dict[str, Any]
            ) -> Any:
                service.update_call_count += 1
                mock_req = MagicMock()
                if eventId not in service.events_db:
                    mock_req.execute.side_effect = Exception("404 Not Found")
                else:
                    service.events_db[eventId] = dict(body)
                    mock_req.execute.return_value = service.events_db[eventId]
                return mock_req

            def delete(self, calendarId: str, eventId: str) -> Any:
                service.delete_call_count += 1
                mock_req = MagicMock()
                if eventId not in service.events_db:
                    mock_req.execute.side_effect = Exception("404 Not Found")
                else:
                    del service.events_db[eventId]
                    mock_req.execute.return_value = {}
                return mock_req

        return EventsResource()


def test_list_events_and_tz_preservation() -> None:
    fake_service = FakeCalendarService()
    fake_service.events_db["evt-1"] = {
        "id": "evt-1",
        "summary": "Math Lecture",
        "start": {"dateTime": "2026-10-10T09:00:00+00:00"},
        "end": {"dateTime": "2026-10-10T10:00:00+00:00"},
    }
    client = CalendarClient(fake_service)
    t_min = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
    t_max = datetime(2026, 10, 10, 23, 59, tzinfo=timezone.utc)

    events = client.list_events(t_min, t_max)
    assert len(events) == 1
    assert events[0].id == "evt-1"
    assert events[0].title == "Math Lecture"
    assert events[0].start.tzinfo is not None
    assert events[0].is_lakshya is False


def test_all_day_event_handling() -> None:
    fake_service = FakeCalendarService()
    fake_service.events_db["all-day-1"] = {
        "id": "all-day-1",
        "summary": "Holiday",
        "start": {"date": "2026-10-12"},
        "end": {"date": "2026-10-12"},
    }
    client = CalendarClient(fake_service)
    t_min = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    t_max = datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc)

    events = client.list_events(t_min, t_max)
    assert len(events) == 1
    assert events[0].title == "Holiday"
    assert events[0].start.tzinfo is not None


def test_lakshya_event_creation_adds_metadata() -> None:
    fake_service = FakeCalendarService()
    client = CalendarClient(fake_service)

    start = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    block = StudyBlock(
        id="block-101",
        task_id="task-1",
        start=start,
        end=end,
        title="Physics Study Block",
    )

    created_evt = client.create_study_block(block)
    assert created_evt.is_lakshya is True
    assert created_evt.title == "Physics Study Block"

    raw = fake_service.events_db[created_evt.id]
    ext_private = raw["extendedProperties"]["private"]
    assert ext_private["lakshya"] == "true"
    assert ext_private["lakshya_block_id"] == "block-101"


def test_lakshya_event_update_succeeds() -> None:
    fake_service = FakeCalendarService()
    client = CalendarClient(fake_service)

    start = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    block1 = StudyBlock(
        id="block-101", task_id="task-1", start=start, end=end, title="Original"
    )
    created = client.create_study_block(block1)

    block2 = StudyBlock(
        id="block-101", task_id="task-1", start=start, end=end, title="Updated Title"
    )
    updated = client.update_study_block(created.id, block2)
    assert updated.title == "Updated Title"
    assert updated.is_lakshya is True


def test_lakshya_event_deletion_succeeds() -> None:
    fake_service = FakeCalendarService()
    client = CalendarClient(fake_service)

    start = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    block = StudyBlock(
        id="block-101", task_id="task-1", start=start, end=end, title="To Delete"
    )
    created = client.create_study_block(block)

    client.delete_study_block(created.id)
    assert created.id not in fake_service.events_db


def test_normal_user_event_update_rejection() -> None:
    """Verify modifying normal user events raises UnauthorizedCalendarMutation."""
    fake_service = FakeCalendarService()
    fake_service.events_db["user_event_99"] = {
        "id": "user_event_99",
        "summary": "Personal Doctor Appointment",
        "start": {"dateTime": "2026-10-15T10:00:00+00:00"},
        "end": {"dateTime": "2026-10-15T11:00:00+00:00"},
        # NOTE: NO lakshya ownership marker!
    }
    client = CalendarClient(fake_service)

    start = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
    block = StudyBlock(
        id="block-99", task_id="task-1", start=start, end=end, title="Hack Attempt"
    )

    with pytest.raises(UnauthorizedCalendarMutation):
        client.update_study_block("user_event_99", block)

    # Verify NO update API execution occurred
    assert fake_service.update_call_count == 0
    raw_item = fake_service.events_db["user_event_99"]
    assert raw_item["summary"] == "Personal Doctor Appointment"


def test_normal_user_event_deletion_rejection() -> None:
    """Verify deleting normal user events raises UnauthorizedCalendarMutation."""
    fake_service = FakeCalendarService()
    fake_service.events_db["user_event_100"] = {
        "id": "user_event_100",
        "summary": "Dentist Visit",
        "start": {"dateTime": "2026-10-16T10:00:00+00:00"},
        "end": {"dateTime": "2026-10-16T11:00:00+00:00"},
        # NOTE: NO lakshya ownership marker!
    }
    client = CalendarClient(fake_service)

    with pytest.raises(UnauthorizedCalendarMutation):
        client.delete_study_block("user_event_100")

    # Verify NO delete API execution occurred
    assert fake_service.delete_call_count == 0
    assert "user_event_100" in fake_service.events_db


def test_missing_event_handling() -> None:
    fake_service = FakeCalendarService()
    client = CalendarClient(fake_service)
    assert client.get_event("nonexistent_id") is None


def test_calendar_api_failure_controlled_exception() -> None:
    fake_service = MagicMock()
    fake_service.events.side_effect = Exception("Google API Network Outage")
    client = CalendarClient(fake_service)

    t_min = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
    t_max = datetime(2026, 10, 10, 23, 59, tzinfo=timezone.utc)

    with pytest.raises(CalendarError, match="Failed to list calendar events"):
        client.list_events(t_min, t_max)
