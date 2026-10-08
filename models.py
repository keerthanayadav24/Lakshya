"""Pydantic v2 domain models for Lakshya study planner."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator


def _validate_non_empty(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _validate_tz_aware(dt: datetime, field_name: str) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return dt


class StudyGoal(BaseModel):
    """Domain model representing a student's academic goal and syllabus."""

    id: str
    title: str
    syllabus_text: str
    deadline: datetime
    created_at: datetime

    @field_validator("id", "title")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)

    @field_validator("syllabus_text")
    @classmethod
    def check_syllabus_length(cls, v: str) -> str:
        if len(v) > 50_000:
            raise ValueError("syllabus_text cannot exceed 50,000 characters")
        return v

    @field_validator("deadline", "created_at")
    @classmethod
    def check_tz_aware(cls, v: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name or "Field"
        return _validate_tz_aware(v, field_name)


class StudyTask(BaseModel):
    """Domain model representing a discrete study task broken down from a goal."""

    id: str
    goal_id: str
    title: str
    estimated_minutes: int
    deadline: datetime
    completed: bool = False

    @field_validator("id", "goal_id", "title")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)

    @field_validator("estimated_minutes")
    @classmethod
    def check_estimated_minutes(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("estimated_minutes must be greater than 0")
        return v

    @field_validator("deadline")
    @classmethod
    def check_tz_aware(cls, v: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name or "Field"
        return _validate_tz_aware(v, field_name)


class StudyBlock(BaseModel):
    """Domain model representing a scheduled study time slot."""

    id: str
    task_id: str
    start: datetime
    end: datetime
    title: str
    source: Literal["lakshya"] = "lakshya"

    @field_validator("id", "task_id", "title")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)

    @field_validator("start", "end")
    @classmethod
    def check_tz_aware(cls, v: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name or "Field"
        return _validate_tz_aware(v, field_name)

    @model_validator(mode="after")
    def check_interval_and_duration(self) -> "StudyBlock":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        duration_minutes = (self.end - self.start).total_seconds() / 60.0
        if duration_minutes > 1440:
            raise ValueError("unreasonable block duration: duration exceeds 24 hours")
        return self


class CalendarEvent(BaseModel):
    """Domain model representing a Google Calendar event."""

    id: str
    start: datetime
    end: datetime
    title: str
    is_lakshya: bool = False

    @field_validator("id", "title")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)

    @field_validator("start", "end")
    @classmethod
    def check_tz_aware(cls, v: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name or "Field"
        return _validate_tz_aware(v, field_name)

    @model_validator(mode="after")
    def check_interval(self) -> "CalendarEvent":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class Plan(BaseModel):
    """Domain model representing a collection of scheduled study blocks for a goal."""

    goal_id: str
    blocks: list[StudyBlock]

    @field_validator("goal_id")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)


class AuditEntry(BaseModel):
    """Domain model representing an audit log entry for human-in-the-loop actions."""

    id: str
    action: str
    timestamp: datetime
    details: dict[str, Any]
    reversible: bool = False

    @field_validator("id", "action")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "Field"
        return _validate_non_empty(v, field_name)

    @field_validator("timestamp")
    @classmethod
    def check_tz_aware(cls, v: datetime, info: ValidationInfo) -> datetime:
        field_name = info.field_name or "Field"
        return _validate_tz_aware(v, field_name)
