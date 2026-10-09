"""Unit tests for plan routes API endpoints."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db import init_db
from main import app


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    db_f = str(tmp_path / "test_plans.db")
    init_db(db_f)
    return db_f


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_create_goal_and_get_latest_endpoint(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)

    # 1. Create Study Goal
    deadline_str = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    syllabus = (
        "Topic 1: Sorting Algorithms\n"
        "Topic 2: Binary Search Trees\n"
        "Topic 3: Graph Traversal"
    )
    payload = {
        "title": "Algorithms & Data Structures",
        "syllabus_text": syllabus,
        "deadline": deadline_str,
    }

    resp = client.post("/api/goals", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["goal"]["title"] == "Algorithms & Data Structures"
    assert len(data["tasks"]) >= 1
    assert len(data["plan"]["blocks"]) >= 1

    # 2. Get Latest Goal
    resp_latest = client.get("/api/goals/latest")
    assert resp_latest.status_code == 200
    latest_data = resp_latest.json()
    assert latest_data["goal"]["title"] == "Algorithms & Data Structures"

    # 3. Get Audits Log
    resp_audits = client.get("/api/audits")
    assert resp_audits.status_code == 200
    audits = resp_audits.json()
    assert len(audits) >= 1
    assert audits[0]["action"] == "CREATE_GOAL"
    assert audits[0]["details"]["goal_id"] == data["goal"]["id"]
    assert audits[0]["details"]["task_count"] == len(data["tasks"])

    # 4. Get Calendar Status
    resp_cal = client.get("/api/calendar/status")
    assert resp_cal.status_code == 200
    assert "connected" in resp_cal.json()


def test_create_goal_validation_errors(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)

    # Past deadline rejection relative to current system time
    past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    past_payload = {
        "title": "Physics",
        "syllabus_text": "Mechanics",
        "deadline": past_deadline,
    }
    resp = client.post("/api/goals", json=past_payload)
    assert resp.status_code == 400


def test_create_goal_preserves_wrapped_topics(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)

    deadline_str = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    syllabus = (
        "1.1 Introduction to Data Analysis: Definition, importance, applications "
        "in industry, Structured vs.\n"
        "unstructured data.\n"
        "1.2 Data Collection & Preprocessing: Importing datasets, Handling missing "
        "values, duplicates, and\n"
        "inconsistencies.\n"
        "1.3 Introduction to Python for Data Analysis: Overview of NumPy, Pandas, "
        "and Matplotlib, Data\n"
        "Frames: Creation, indexing, filtering."
    )
    payload = {
        "title": "Data Analysis Course",
        "syllabus_text": syllabus,
        "deadline": deadline_str,
    }

    resp = client.post("/api/goals", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    tasks = data["tasks"]
    assert len(tasks) == 3
    assert "Introduction to Data Analysis" in tasks[0]["title"]
    assert tasks[0]["description"] is None or "Structured vs. unstructured data." in (
        tasks[0]["description"] or tasks[0]["title"]
    )
    assert "Data Collection & Preprocessing" in tasks[1]["title"]
    assert "duplicates, and inconsistencies." in (
        tasks[1]["description"] or tasks[1]["title"]
    )
    assert "Introduction to Python" in tasks[2]["title"]
    assert "Creation, indexing, filtering." in (
        tasks[2]["description"] or tasks[2]["title"]
    )


def test_get_latest_goal_multiple_history(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)
    deadline_str = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

    # 1. Create first goal (older)
    payload1 = {
        "title": "First Historical Goal",
        "syllabus_text": "Topic A: Algebra\nTopic B: Geometry",
        "deadline": deadline_str,
    }
    resp1 = client.post("/api/goals", json=payload1)
    assert resp1.status_code == 201

    # 2. Create second goal (newer)
    payload2 = {
        "title": "Second Latest Goal",
        "syllabus_text": (
            "1.1 Introduction to Data Analysis: Structured vs. unstructured data.\n"
            "1.2 Data Collection: Datasets and missing values.\n"
            "1.3 Python Basics: NumPy and Pandas."
        ),
        "deadline": deadline_str,
    }
    resp2 = client.post("/api/goals", json=payload2)
    assert resp2.status_code == 201

    # 3. GET /api/goals/latest returns second (newest) goal
    resp_latest = client.get("/api/goals/latest")
    assert resp_latest.status_code == 200
    latest_data = resp_latest.json()
    assert latest_data["goal"]["title"] == "Second Latest Goal"
    assert len(latest_data["tasks"]) == 3


def test_create_goal_mixed_data_science_syllabus(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)
    deadline_str = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

    syllabus = (
        "Course: Data Science 101\n"
        "\n"
        "Module 1: Data Analysis Fundamentals\n"
        "1.1 Introduction to Data Analysis: Overview of data types, data structures, "
        "and the data science lifecycle. Basic data manipulation with Pandas.\n"
        "1.2 Data Collection & Preprocessing: Techniques for importing data, "
        "handling missing values, and data cleaning.\n"
        "Feature extraction and selection techniques.\n"
        "\n"
        "Module 2: Machine Learning\n"
        "* Introduction to Python for Data Analysis: Python syntax, "
        "control structures, and standard libraries."
    )

    payload = {
        "title": "Data Science 101",
        "syllabus_text": syllabus,
        "deadline": deadline_str,
    }

    resp = client.post("/api/goals", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    tasks = data["tasks"]
    assert len(tasks) == 3

    # Task 1
    assert tasks[0]["title"] == "Introduction to Data Analysis"
    assert tasks[0]["description"] is not None
    assert "Overview of data types" in tasks[0]["description"]

    # Task 2
    assert tasks[1]["title"] == "Data Collection & Preprocessing"
    assert tasks[1]["description"] is not None
    assert "Feature extraction and selection techniques." in tasks[1]["description"]

    # Task 3
    assert tasks[2]["title"] == "Introduction to Python for Data Analysis"
    assert tasks[2]["description"] is not None
    assert "Python syntax" in tasks[2]["description"]

    # Scheduled blocks verification
    blocks = data["plan"]["blocks"]
    assert len(blocks) >= 3
    scheduled_task_ids = {b["task_id"] for b in blocks}
    expected_task_ids = {t["id"] for t in tasks}
    assert scheduled_task_ids == expected_task_ids

    # Audit logging verification
    resp_audits = client.get("/api/audits")
    assert resp_audits.status_code == 200
    audits = resp_audits.json()
    assert len(audits) >= 1
    latest_audit = audits[0]
    assert latest_audit["action"] == "CREATE_GOAL"
    assert latest_audit["details"]["goal_id"] == data["goal"]["id"]
    assert latest_audit["details"]["task_count"] == 3


def test_create_goal_full_five_module_syllabus(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)
    deadline_str = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

    full_ds_syllabus = (
        "Course: Introduction to Data Science\n\n"
        "Module 1: Data Analysis Fundamentals\n"
        "1.1 Introduction to Data Analysis: Definition, importance, industry "
        "applications, and structured vs. unstructured data.\n"
        "1.2 Data Collection & Preprocessing: Importing datasets, handling missing "
        "values, duplicates, and inconsistencies.\n"
        "Feature extraction and selection techniques.\n\n"
        "Module 2: Python for Data Analysis\n"
        "Python Libraries: NumPy, Pandas, and Matplotlib.\n"
        "DataFrames: Creation, indexing, filtering, and aggregation.\n"
        "2.3 Data Visualization: Bar charts, histograms, scatter plots, "
        "and box plots.\n\n"
        "Module 3: Statistics and Probability\n"
        "Descriptive Statistics: Mean, median, mode, variance, and "
        "standard deviation.\n"
        "Probability Distributions: Normal distribution, binomial distribution, and "
        "Bayes' theorem.\n"
        "Hypothesis Testing: Null and alternative hypotheses, p-values, and "
        "significance level (α = 0.05).\n\n"
        "Module 4: Machine Learning Basics\n"
        "- Supervised Learning: Regression and classification.\n"
        "- Unsupervised Learning: Clustering and dimensionality reduction.\n"
        "- Model Evaluation: Accuracy, precision, recall, F1-score, and overfitting "
        "vs. underfitting.\n\n"
        "Module 5: Practical Applications\n"
        "Case Study: Analyze a dataset containing 10,000 customer records.\n"
        "Data Cleaning: Handle 5% missing values and duplicate records.\n"
        "Final Project: Build a Python dashboard using Pandas and Matplotlib."
    )

    payload = {
        "title": "Complete Data Science Course",
        "syllabus_text": full_ds_syllabus,
        "deadline": deadline_str,
    }

    resp = client.post("/api/goals", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    tasks = data["tasks"]
    assert len(tasks) == 14

    task_titles = [t["title"] for t in tasks]
    assert "Python Libraries" in task_titles
    assert "DataFrames" in task_titles
    assert "Case Study" in task_titles
    assert "Data Cleaning" in task_titles
    assert "Final Project" in task_titles

    # Audit entry verification
    resp_audits = client.get("/api/audits")
    assert resp_audits.status_code == 200
    audits = resp_audits.json()
    latest_audit = audits[0]
    assert latest_audit["action"] == "CREATE_GOAL"
    assert latest_audit["details"]["task_count"] == 14


def test_create_goal_exceeding_task_limit_rejection(
    tmp_db_path: str, base_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_db_path}")

    client = TestClient(app)
    deadline_str = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

    # Create 55 numbered topics
    oversized_syllabus = "\n".join(
        f"Topic {i}: Overview of study topic number {i}." for i in range(1, 56)
    )

    payload = {
        "title": "Oversized Goal",
        "syllabus_text": oversized_syllabus,
        "deadline": deadline_str,
    }

    resp = client.post("/api/goals", json=payload)
    assert resp.status_code == 400
    assert "exceeding the maximum limit of 50 tasks" in resp.json()["detail"]




