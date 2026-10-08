# Lakshya 🎯

An autonomous study-planning agent for students built for the 6-hour hackathon (Track: *AI Personal Assistant & Autonomous Agents*).

## Problem & Solution

Students often struggle to translate a heavy course syllabus and impending academic deadlines into actionable, realistic daily study routines around their existing calendar commitments. 

**Lakshya** solves this by combining:
1. **Intelligent Syllabus Breakdown:** Gemini Flash decomposes course content into structured study tasks.
2. **Deterministic Python Scheduling:** Algorithmic calculation of study blocks respecting daily limits, rest windows, and hard deadlines.
3. **Human-in-the-Loop Oversight:** Explicit student approval required before modifying Google Calendar, with complete audit logging and reversible actions.

## Phase 2 Integrations

- **Google OAuth:** Used strictly for Google Calendar authorization (`https://www.googleapis.com/auth/calendar`). Cryptographic state token validation prevents state tampering.
- **Google Calendar Client:** Isolated wrapper around Google Calendar API. All mutations (create, update, delete) are strictly guarded by private extended properties (`lakshya = "true"`). Non-Lakshya user events cannot be modified or deleted.
- **Gemini Flash Client:** Isolated LLM wrapper for task breakdown and messaging. Operates statelessly with strict API key configuration safety. Does not have access to calendar tools or mutation methods.
- **Environment Configuration:** Real credentials must be supplied via environment variables (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GEMINI_API_KEY`).
- **Offline Mocked Tests:** All unit tests mock external services and run completely offline.

> **Note:** Syllabus task breakdown prompts, automatic scheduling algorithms, agent loop, and approval workflows will be implemented in Phase 3+.

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
