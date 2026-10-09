"""Syllabus task breakdown service using Gemini Flash LLM."""

from datetime import datetime

from guards.output_validation import parse_task_breakdown
from llm.gemini import GeminiClient
from llm.prompts import SYLLABUS_BREAKDOWN_SYSTEM_INSTRUCTION
from models import StudyTask


def breakdown_syllabus(
    *,
    goal_id: str,
    syllabus_text: str,
    deadline: datetime,
    gemini_client: GeminiClient,
) -> list[StudyTask]:
    """Break down syllabus content into StudyTask domain models using Gemini Flash."""
    if not goal_id or not goal_id.strip():
        raise ValueError("goal_id cannot be empty")
    if not syllabus_text or not syllabus_text.strip():
        raise ValueError("syllabus_text cannot be empty")
    if len(syllabus_text) > 50_000:
        raise ValueError("syllabus_text cannot exceed 50,000 characters")
    if deadline.tzinfo is None or deadline.tzinfo.utcoffset(deadline) is None:
        raise ValueError("deadline must be timezone-aware")

    # Request JSON generation from Gemini Flash
    raw_json = gemini_client.generate_json(
        system_instruction=SYLLABUS_BREAKDOWN_SYSTEM_INSTRUCTION,
        user_input=syllabus_text,
    )

    # Strictly parse and validate LLM JSON response
    breakdown = parse_task_breakdown(raw_json)

    # Convert to domain StudyTask objects
    tasks: list[StudyTask] = []
    for idx, item in enumerate(breakdown.tasks, start=1):
        task = StudyTask(
            id=f"task_{goal_id}_{idx}",
            goal_id=goal_id,
            title=item.title,
            estimated_minutes=item.estimated_minutes,
            deadline=deadline,
            completed=False,
        )
        tasks.append(task)

    return tasks
