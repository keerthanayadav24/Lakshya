"""FastAPI routes for Lakshya study goals and scheduling."""

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from config import settings
from db import (
    _get_db_path,
    get_audit_entries,
    get_tasks,
    save_audit,
    save_goal,
    save_task,
)
from llm.gemini import GeminiClient
from llm.task_breakdown import (
    breakdown_syllabus,
    derive_fallback_title_and_description,
    parse_syllabus_topics,
)
from models import AuditEntry, Plan, StudyGoal, StudyTask
from planner.policies import SchedulingPolicy
from planner.scheduler import schedule_tasks
from tools.google_auth import load_credentials

router = APIRouter(prefix="/api", tags=["plans"])


class CreateGoalRequest(BaseModel):
    """Payload for creating a new study goal from syllabus text."""

    title: str = Field(..., min_length=1, max_length=200)
    syllabus_text: str = Field(..., min_length=1, max_length=50_000)
    deadline: datetime

    @field_validator("title", "syllabus_text")
    @classmethod
    def check_non_empty(cls, v: str, info: ValidationInfo) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()

    @field_validator("deadline")
    @classmethod
    def check_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("deadline must be timezone-aware")
        return v


class GoalResponse(BaseModel):
    """Response returned after breaking down syllabus and scheduling study tasks."""

    goal: StudyGoal
    tasks: list[StudyTask]
    plan: Plan


class CalendarStatusResponse(BaseModel):
    """Response model for Google Calendar connection status."""

    connected: bool
    details: str


@router.post(
    "/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED
)
async def create_study_goal(req: CreateGoalRequest) -> GoalResponse:
    """Create a new study goal, generate task breakdown, and schedule study blocks."""
    now = datetime.now(timezone.utc)
    if req.deadline <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deadline must be in the future",
        )

    goal_id = f"g_{uuid4().hex[:8]}"
    goal = StudyGoal(
        id=goal_id,
        title=req.title,
        syllabus_text=req.syllabus_text,
        deadline=req.deadline,
        created_at=now,
    )

    save_goal(goal)

    tasks: list[StudyTask] = []
    # If Gemini API key is configured, use Gemini breakdown
    if settings.gemini_api_key and settings.gemini_api_key.strip():
        try:
            gemini_client = GeminiClient(api_key=settings.gemini_api_key)
            tasks = breakdown_syllabus(
                goal_id=goal_id,
                syllabus_text=req.syllabus_text,
                deadline=req.deadline,
                gemini_client=gemini_client,
            )
        except Exception:
            # Fallback to deterministic topic breakdown if Gemini service fails
            tasks = _fallback_task_breakdown(goal_id, req.syllabus_text, req.deadline)
    else:
        # Fallback to deterministic topic breakdown when API key is unconfigured
        tasks = _fallback_task_breakdown(goal_id, req.syllabus_text, req.deadline)

    for task in tasks:
        save_task(task)

    policy = SchedulingPolicy(
        study_block_minutes=50,
        max_daily_minutes=settings.max_daily_study_minutes,
    )
    plan = schedule_tasks(
        tasks=tasks,
        existing_events=[],
        now=now,
        policy=policy,
    )

    audit_entry = AuditEntry(
        id=f"audit_{uuid4().hex[:8]}",
        action="CREATE_GOAL",
        timestamp=now,
        details={
            "goal_id": goal_id,
            "title": req.title,
            "task_count": len(tasks),
            "scheduled_blocks": len(plan.blocks),
        },
        reversible=False,
    )
    save_audit(audit_entry)

    return GoalResponse(goal=goal, tasks=tasks, plan=plan)


@router.get("/goals/latest", response_model=GoalResponse)
async def get_latest_goal() -> GoalResponse:
    """Retrieve the most recent goal, its tasks, and scheduled plan."""
    path = _get_db_path()
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, syllabus_text, deadline, created_at
            FROM goals ORDER BY created_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No study goals found",
            )
        goal = StudyGoal(
            id=row[0],
            title=row[1],
            syllabus_text=row[2],
            deadline=datetime.fromisoformat(row[3]),
            created_at=datetime.fromisoformat(row[4]),
        )

    tasks = get_tasks(goal.id)
    now = datetime.now(timezone.utc)
    policy = SchedulingPolicy(
        study_block_minutes=50,
        max_daily_minutes=settings.max_daily_study_minutes,
    )
    try:
        plan = schedule_tasks(
            tasks=tasks,
            existing_events=[],
            now=now,
            policy=policy,
        )
    except Exception:
        plan = Plan(goal_id=goal.id, blocks=[])

    return GoalResponse(goal=goal, tasks=tasks, plan=plan)


@router.get("/audits", response_model=list[AuditEntry])
async def get_audits() -> list[AuditEntry]:
    """Retrieve audit history log."""
    return get_audit_entries()


@router.get("/calendar/status", response_model=CalendarStatusResponse)
async def get_calendar_status() -> CalendarStatusResponse:
    """Check if Google Calendar OAuth credentials are configured and valid."""
    creds = load_credentials()
    if creds and creds.get("token"):
        return CalendarStatusResponse(
            connected=True,
            details="Google Calendar API connected",
        )
    return CalendarStatusResponse(
        connected=False,
        details="Calendar credentials not linked",
    )


def _fallback_task_breakdown(
    goal_id: str, syllabus_text: str, deadline: datetime
) -> list[StudyTask]:
    """Deterministic fallback task generator when Gemini LLM is unavailable."""
    topics = parse_syllabus_topics(syllabus_text)
    if not topics:
        topics = ["Core Study Material Review"]

    if len(topics) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Syllabus breakdown produced {len(topics)} tasks, "
                "exceeding the maximum limit of 50 tasks."
            ),
        )

    tasks: list[StudyTask] = []
    for idx, topic in enumerate(topics, start=1):
        title, desc = derive_fallback_title_and_description(topic)

        tasks.append(
            StudyTask(
                id=f"task_{goal_id}_{idx}",
                goal_id=goal_id,
                title=title,
                description=desc,
                estimated_minutes=50,
                deadline=deadline,
                completed=False,
            )
        )
    return tasks
