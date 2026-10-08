"""SQLite database layer for Lakshya."""

import json
import sqlite3
from datetime import datetime
from typing import Any

from config import settings
from models import AuditEntry, StudyGoal, StudyTask


def _get_db_path(db_path: str | None = None) -> str:
    if db_path is not None:
        return db_path
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return "lakshya.db"


def init_db(db_path: str | None = None) -> None:
    """Initialize SQLite database tables."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                syllabus_text TEXT NOT NULL,
                deadline TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                estimated_minutes INTEGER NOT NULL,
                deadline TEXT NOT NULL,
                completed INTEGER NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_entries (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT NOT NULL,
                reversible INTEGER NOT NULL
            );
            """
        )
        conn.commit()


def save_goal(goal: StudyGoal, db_path: str | None = None) -> None:
    """Save or update a StudyGoal in SQLite."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO goals (id, title, syllabus_text, deadline, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                syllabus_text = excluded.syllabus_text,
                deadline = excluded.deadline,
                created_at = excluded.created_at;
            """,
            (
                goal.id,
                goal.title,
                goal.syllabus_text,
                goal.deadline.isoformat(),
                goal.created_at.isoformat(),
            ),
        )
        conn.commit()


def get_goal(goal_id: str, db_path: str | None = None) -> StudyGoal | None:
    """Retrieve a StudyGoal by ID."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, syllabus_text, deadline, created_at
            FROM goals WHERE id = ?
            """,
            (goal_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return StudyGoal(
            id=row[0],
            title=row[1],
            syllabus_text=row[2],
            deadline=datetime.fromisoformat(row[3]),
            created_at=datetime.fromisoformat(row[4]),
        )


def save_task(task: StudyTask, db_path: str | None = None) -> None:
    """Save or update a StudyTask in SQLite."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                id, goal_id, title, estimated_minutes, deadline, completed
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goal_id = excluded.goal_id,
                title = excluded.title,
                estimated_minutes = excluded.estimated_minutes,
                deadline = excluded.deadline,
                completed = excluded.completed;
            """,
            (
                task.id,
                task.goal_id,
                task.title,
                task.estimated_minutes,
                task.deadline.isoformat(),
                1 if task.completed else 0,
            ),
        )
        conn.commit()


def get_tasks(goal_id: str, db_path: str | None = None) -> list[StudyTask]:
    """Retrieve all StudyTasks for a specific goal."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, goal_id, title, estimated_minutes, deadline, completed
            FROM tasks WHERE goal_id = ?
            """,
            (goal_id,),
        )
        rows = cursor.fetchall()
        return [
            StudyTask(
                id=row[0],
                goal_id=row[1],
                title=row[2],
                estimated_minutes=row[3],
                deadline=datetime.fromisoformat(row[4]),
                completed=bool(row[5]),
            )
            for row in rows
        ]


def save_audit(entry: AuditEntry, db_path: str | None = None) -> None:
    """Save an AuditEntry in SQLite."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_entries (id, action, timestamp, details, reversible)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                action = excluded.action,
                timestamp = excluded.timestamp,
                details = excluded.details,
                reversible = excluded.reversible;
            """,
            (
                entry.id,
                entry.action,
                entry.timestamp.isoformat(),
                json.dumps(entry.details),
                1 if entry.reversible else 0,
            ),
        )
        conn.commit()


def get_audit_entries(db_path: str | None = None) -> list[AuditEntry]:
    """Retrieve all AuditEntry records."""
    path = _get_db_path(db_path)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, action, timestamp, details, reversible
            FROM audit_entries ORDER BY timestamp ASC
            """
        )
        rows = cursor.fetchall()
        entries: list[AuditEntry] = []
        for row in rows:
            details_dict: dict[str, Any] = json.loads(row[3])
            entries.append(
                AuditEntry(
                    id=row[0],
                    action=row[1],
                    timestamp=datetime.fromisoformat(row[2]),
                    details=details_dict,
                    reversible=bool(row[4]),
                )
            )
        return entries
