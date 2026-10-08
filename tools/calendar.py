"""Google Calendar API client wrapper with Lakshya ownership guards."""

from datetime import datetime, timezone
from typing import Any

from models import CalendarEvent, StudyBlock


class UnauthorizedCalendarMutation(Exception):
    """Raised when an operation attempts to modify or delete a non-Lakshya event."""

    pass


class CalendarError(Exception):
    """Raised when Google Calendar API operations fail."""

    pass


def _raw_to_calendar_event(raw: dict[str, Any]) -> CalendarEvent:
    """Convert raw Google Calendar API event dict to CalendarEvent domain model."""
    event_id = raw.get("id", "")
    title = raw.get("summary") or raw.get("title") or "Untitled Event"
    ext_private = raw.get("extendedProperties", {}).get("private", {})
    is_lakshya = ext_private.get("lakshya") == "true"

    start_info = raw.get("start", {})
    end_info = raw.get("end", {})

    try:
        if "dateTime" in start_info:
            start_dt = datetime.fromisoformat(start_info["dateTime"])
        elif "date" in start_info:
            dt = datetime.strptime(start_info["date"], "%Y-%m-%d")
            start_dt = dt.replace(tzinfo=timezone.utc)
        else:
            raise CalendarError(f"Event {event_id} missing start time")

        if "dateTime" in end_info:
            end_dt = datetime.fromisoformat(end_info["dateTime"])
        elif "date" in end_info:
            dt = datetime.strptime(end_info["date"], "%Y-%m-%d")
            end_dt = dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            raise CalendarError(f"Event {event_id} missing end time")

        # Ensure timezone awareness
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        if end_dt <= start_dt:
            end_dt = start_dt.replace(hour=23, minute=59, second=59)

        return CalendarEvent(
            id=event_id,
            start=start_dt,
            end=end_dt,
            title=title,
            is_lakshya=is_lakshya,
        )
    except Exception as e:
        if isinstance(e, CalendarError):
            raise
        raise CalendarError(f"Failed to parse calendar event data: {e}") from e


class CalendarClient:
    """Safely interacts with Google Calendar API while protecting non-Lakshya events."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CalendarEvent]:
        """Fetch all calendar events within time_min and time_max."""
        try:
            time_min_str = time_min.isoformat()
            time_max_str = time_max.isoformat()
            response = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min_str,
                    timeMax=time_max_str,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items = response.get("items", [])
            return [_raw_to_calendar_event(item) for item in items]
        except Exception as e:
            raise CalendarError(f"Failed to list calendar events: {e}") from e

    def get_event(
        self,
        event_id: str,
    ) -> CalendarEvent | None:
        """Fetch a specific event by ID, or return None if not found."""
        try:
            raw = (
                self.service.events()
                .get(
                    calendarId="primary",
                    eventId=event_id,
                )
                .execute()
            )
            if not raw:
                return None
            return _raw_to_calendar_event(raw)
        except Exception as e:
            # Handle not found or service errors safely
            if "404" in str(e) or "notFound" in str(e):
                return None
            raise CalendarError(f"Failed to retrieve event {event_id}: {e}") from e

    def _get_raw_event(self, event_id: str) -> dict[str, Any] | None:
        """Internal helper to get raw event data."""
        try:
            return (
                self.service.events()
                .get(
                    calendarId="primary",
                    eventId=event_id,
                )
                .execute()
            )
        except Exception as e:
            if "404" in str(e) or "notFound" in str(e):
                return None
            raise CalendarError(f"Failed to retrieve event {event_id}: {e}") from e

    def create_study_block(
        self,
        block: StudyBlock,
    ) -> CalendarEvent:
        """Create a new Lakshya study block on Google Calendar with metadata."""
        try:
            body = {
                "summary": block.title,
                "start": {"dateTime": block.start.isoformat()},
                "end": {"dateTime": block.end.isoformat()},
                "extendedProperties": {
                    "private": {
                        "lakshya": "true",
                        "lakshya_block_id": block.id,
                    }
                },
            }
            raw = (
                self.service.events()
                .insert(
                    calendarId="primary",
                    body=body,
                )
                .execute()
            )
            return _raw_to_calendar_event(raw)
        except Exception as e:
            raise CalendarError(f"Failed to create study block event: {e}") from e

    def update_study_block(
        self,
        event_id: str,
        block: StudyBlock,
    ) -> CalendarEvent:
        """Update an existing Lakshya study block event after verifying ownership."""
        raw = self._get_raw_event(event_id)
        if not raw:
            raise CalendarError(f"Event {event_id} not found")

        ext_private = raw.get("extendedProperties", {}).get("private", {})
        if ext_private.get("lakshya") != "true":
            raise UnauthorizedCalendarMutation(
                f"Cannot update non-Lakshya calendar event {event_id}"
            )

        try:
            raw["summary"] = block.title
            raw["start"] = {"dateTime": block.start.isoformat()}
            raw["end"] = {"dateTime": block.end.isoformat()}

            updated = (
                self.service.events()
                .update(
                    calendarId="primary",
                    eventId=event_id,
                    body=raw,
                )
                .execute()
            )
            return _raw_to_calendar_event(updated)
        except Exception as e:
            if isinstance(e, UnauthorizedCalendarMutation):
                raise
            raise CalendarError(f"Failed to update study block event: {e}") from e

    def delete_study_block(
        self,
        event_id: str,
    ) -> None:
        """Delete an existing Lakshya study block event after verifying ownership."""
        raw = self._get_raw_event(event_id)
        if not raw:
            raise CalendarError(f"Event {event_id} not found")

        ext_private = raw.get("extendedProperties", {}).get("private", {})
        if ext_private.get("lakshya") != "true":
            raise UnauthorizedCalendarMutation(
                f"Cannot delete non-Lakshya calendar event {event_id}"
            )

        try:
            self.service.events().delete(
                calendarId="primary",
                eventId=event_id,
            ).execute()
        except Exception as e:
            if isinstance(e, UnauthorizedCalendarMutation):
                raise
            raise CalendarError(f"Failed to delete study block event: {e}") from e
