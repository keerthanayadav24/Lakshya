"""Tests for Google OAuth 2.0 API routes."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_oauth_start_redirects_and_sets_cookie() -> None:
    """Test that /oauth/start returns a redirect and sets oauth_state cookie."""
    response = client.get("/oauth/start", follow_redirects=False)
    assert response.status_code == 307
    assert "location" in response.headers
    assert "accounts.google.com/o/oauth2/auth" in response.headers["location"]

    # Check that cookie is set
    assert "oauth_state" in response.cookies
    assert len(response.cookies["oauth_state"]) > 0


def test_oauth_callback_error_query_param() -> None:
    """Test callback handles explicit error from Google."""
    response = client.get("/oauth/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 400
    assert "denied or failed" in response.json()["detail"]


def test_oauth_callback_missing_code_or_state() -> None:
    """Test callback rejects request missing code or state."""
    response = client.get("/oauth/callback?code=abc", follow_redirects=False)
    assert response.status_code == 400
    assert "Missing authorization code" in response.json()["detail"]

    response = client.get("/oauth/callback?state=def", follow_redirects=False)
    assert response.status_code == 400
    assert "Missing authorization code" in response.json()["detail"]


def test_oauth_callback_missing_cookie() -> None:
    """Test callback rejects request missing the oauth_state cookie."""
    local_client = TestClient(app)
    response = local_client.get("/oauth/callback?code=abc&state=def", follow_redirects=False)  # noqa: E501
    assert response.status_code == 400
    assert "cookie missing or expired" in response.json()["detail"]


@patch("api.auth_routes.exchange_code_for_credentials")
def test_oauth_callback_state_mismatch(mock_exchange: MagicMock) -> None:
    """Test callback handles state mismatch."""
    mock_exchange.side_effect = ValueError("State mismatch")

    response = client.get(
        "/oauth/callback?code=abc&state=bad_state",
        cookies={"oauth_state": "good_state"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "validation failed" in response.json()["detail"]


@patch("api.auth_routes.exchange_code_for_credentials")
def test_oauth_callback_exchange_failure(mock_exchange: MagicMock) -> None:
    """Test callback handles exchange exception safely."""
    mock_exchange.side_effect = Exception("Google API error")

    response = client.get(
        "/oauth/callback?code=abc&state=good_state",
        cookies={"oauth_state": "good_state"},
        follow_redirects=False,
    )
    assert response.status_code == 500
    assert "Failed to exchange authorization code" in response.json()["detail"]
    assert "Google API error" not in response.json()["detail"]


@patch("api.auth_routes.save_credentials")
@patch("api.auth_routes.exchange_code_for_credentials")
def test_oauth_callback_success(
    mock_exchange: MagicMock, mock_save: MagicMock
) -> None:
    """Test successful token exchange and credential persistence."""
    mock_exchange.return_value = {
        "token": "fake_token", 
        "refresh_token": "fake_refresh"
    }

    response = client.get(
        "/oauth/callback?code=abc&state=good_state",
        cookies={"oauth_state": "good_state"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Authentication Successful" in response.text

    mock_exchange.assert_called_once_with(
        code="abc",
        expected_state="good_state",
        received_state="good_state",
    )
    mock_save.assert_called_once_with(
        {"token": "fake_token", "refresh_token": "fake_refresh"}
    )
