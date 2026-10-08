# Lakshya 🎯

An autonomous study-planning agent for students built for the 6-hour hackathon (Track: *AI Personal Assistant & Autonomous Agents*).

## Problem & Solution

Students often struggle to translate a heavy course syllabus and impending academic deadlines into actionable, realistic daily study routines around their existing calendar commitments. 

**Lakshya** solves this by combining:
1. **Intelligent Syllabus Breakdown:** Gemini Flash decomposes course content into structured study tasks.
2. **Deterministic Python Scheduling:** Algorithmic calculation of study blocks respecting daily limits, rest windows, and hard deadlines.
3. **Human-in-the-Loop Oversight:** Explicit student approval required before modifying Google Calendar, with complete audit logging and reversible actions.

> **Note:** Integration with Google OAuth, Google Calendar API, and Gemini API is planned for upcoming phases and is **NOT** implemented in Phase 1.

## Technology Stack

- **Backend:** Python 3.10+, FastAPI, Pydantic v2, SQLite
- **LLM:** Gemini API / Gemini Flash (Planned for Phase 2+)
- **Google Services:** Google OAuth, Google Calendar API (Planned for Phase 2+)
- **Frontend:** Semantic HTML5, Vanilla CSS, Vanilla JavaScript (served directly by FastAPI)
- **Quality & Testing:** pytest, Hypothesis, Ruff, mypy, GitHub Actions CI

## Phase 1 Scope

This baseline repository skeleton establishes:
- Pydantic v2 domain models (`StudyGoal`, `StudyTask`, `StudyBlock`, `CalendarEvent`, `Plan`, `AuditEntry`)
- SQLite database foundation
- Environment configuration system
- FastAPI server with `/health` and static frontend placeholder
- Testing suite (`pytest`, `mypy`, `ruff`) and CI workflow

## Local Setup & Development

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Run Quality Checks
```bash
# Check formatting and linting
ruff check .

# Run type checker
mypy .

# Run offline unit tests
pytest
```

### 3. Run Application Locally
```bash
python -m uvicorn main:app --reload
```

Access the app at:
- Web App: `http://127.0.0.1:8000/`
- Health Check: `http://127.0.0.1:8000/health`
