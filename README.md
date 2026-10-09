# Lakshya 🎯

An autonomous study-planning agent for students built for the 6-hour hackathon (Track: *AI Personal Assistant & Autonomous Agents*).

## Problem & Solution

Students often struggle to translate a heavy course syllabus and impending academic deadlines into actionable, realistic daily study routines around their existing calendar commitments. 

**Lakshya** solves this by combining:
1. **Intelligent Syllabus Breakdown:** Gemini Flash decomposes course content into structured study tasks.
2. **Deterministic Python Scheduling:** Algorithmic calculation of study blocks respecting daily limits, rest windows, and hard deadlines.
3. **Human-in-the-Loop Oversight:** Explicit student approval required before modifying Google Calendar, with complete audit logging and reversible actions.

## Agent Loop (Phase 5)

Lakshya operates on an autonomous **Observe → Reason → Propose → Approve → Execute → Audit → Undo** architecture:

- **Observe:** Detects past missed Lakshya-owned study blocks (`end < now` and `is_lakshya is True`). Normal user calendar events are never flagged.
- **Reason:** Calculates replacement study blocks using the 100% deterministic Python scheduler engine. Gemini is **NOT** used for replanning.
- **Propose:** Generates a persistent `ReplanProposal` with status `pending`. **ZERO** Google Calendar mutations occur during proposal creation.
- **Approve:** Requires explicit student confirmation (`POST /api/proposals/{id}/approve` with `approved: true`).
- **Execute:** Mutates **ONLY** Lakshya-owned Google Calendar events (`lakshya = "true"`). Non-Lakshya user events are strictly protected and never modified.
- **Audit:** Records immutable audit log entries (`proposal_created`, `proposal_applied`, `proposal_rejected`, `proposal_undone`, `proposal_failed`) for all state transitions.
- **Undo:** Safely reverses applied proposals (`POST /api/proposals/{id}/undo`), removing newly created Lakshya blocks and restoring original blocks.

> **CRITICAL HUMAN-IN-THE-LOOP RULE:**
> *"Calendar changes are never made merely because the agent proposed them. The student must explicitly approve the proposal."*

## Gemini Task Breakdown (Phase 4)

- **Syllabus Content Analysis:** Gemini Flash is used solely to parse course syllabi into structured study tasks (`LLMTaskBreakdown`).
- **Strict Schema Validation:** LLM output is validated using Pydantic (`LLMTask` & `LLMTaskBreakdown`). Output must strictly contain non-empty titles (max 200 chars) and estimated minutes (10 to 480 mins).
- **Strict Guard (`parse_task_breakdown`):** Markdown code fences, malformed JSON, missing fields, or extra fields are strictly rejected via `OutputValidationError`. No partial parsing or coercion fallback.
- **Strict Architectural Separation:** Gemini ONLY determines *WHAT* needs to be studied. Gemini does **NOT** determine *WHEN* tasks are scheduled, calendar dates, times, availability, or calendar mutations.

## Deterministic Scheduler (Phase 3)

The core Lakshya scheduling engine is **100% pure deterministic Python**.

- **Gemini does NOT schedule:** LLMs are strictly excluded from date/time calculations, calendar availability analysis, and block placement decisions.
- **Python Performs Scheduling:** Greedy deterministic search algorithm translates tasks into fixed-duration study blocks (`policy.study_block_minutes`).
- **Calendar Events as Busy Time:** All existing Google Calendar events (and previously created Lakshya events) are treated as non-negotiable busy intervals.
- **Daily Study Limits:** Enforces `policy.max_daily_minutes` (default 240 mins/day) specifically for generated study blocks.
- **Mandatory Rest Windows:** Enforces configured rest periods (default 22:00 to 07:00). Blocks crossing rest boundaries are strictly rejected.
- **Deadlines Enforced:** Every generated block must complete on or before its task deadline. If tasks cannot fit, `SchedulingImpossible` is raised.
- **Input Immutability & Determinism:** Identical inputs yield identical plans. Input task/event list order does not affect output.
- **Property-Based Verification:** Verified using Hypothesis property tests across 10 critical scheduling invariants.

## Phase 2 Integrations

- **Google OAuth:** Used strictly for Google Calendar authorization (`https://www.googleapis.com/auth/calendar`). Cryptographic state token validation prevents state tampering.
- **Google Calendar Client:** Isolated wrapper around Google Calendar API. All mutations (create, update, delete) are strictly guarded by private extended properties (`lakshya = "true"`). Non-Lakshya user events cannot be modified or deleted.
- **Gemini Flash Client:** Isolated LLM wrapper for task breakdown and messaging. Operates statelessly with strict API key configuration safety. Does not have access to calendar tools or mutation methods.
- **Environment Configuration:** Real credentials must be supplied via environment variables (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GEMINI_API_KEY`).
- **Offline Mocked Tests:** All unit tests mock external services and run completely offline.

## Technology Stack

- **Backend:** Python 3.10+, FastAPI, Pydantic v2, SQLite
- **LLM:** Gemini API / Gemini Flash (`google-genai` SDK)
- **Google Services:** Google OAuth (`google-auth-oauthlib`), Google Calendar API (`google-api-python-client`)
- **Frontend:** Semantic HTML5, Vanilla CSS, Vanilla JavaScript (served directly by FastAPI)
- **Quality & Testing:** pytest, Hypothesis, Ruff, mypy, GitHub Actions CI

## Local Setup & Development

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Environment Setup
Copy `.env.example` to `.env` and fill in your credentials when running with live services:
```bash
cp .env.example .env
```

### 3. Run Quality Checks
```bash
# Check formatting and linting
ruff check .

# Run type checker
mypy .

# Run offline unit tests
pytest
```

### 4. Run Application Locally
```bash
python -m uvicorn main:app --reload
```

Access the app at:
- Web App: `http://127.0.0.1:8000/`
- Health Check: `http://127.0.0.1:8000/health`
