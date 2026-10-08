"""Health check endpoint tests for Lakshya FastAPI app."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    """Test GET /health returns 200 OK and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint() -> None:
    """Test GET / serves index.html content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>Lakshya" in response.text
