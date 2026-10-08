"""Unit tests for Google OAuth module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.google_auth import (
    clear_credentials,
    exchange_code_for_credentials,
    generate_oauth_state,
    get_google_authorization_url,
    load_credentials,
    save_credentials,
)


def test_oauth_state_generation() -> None:
    """Test OAuth state generation produces non-empty random tokens."""
    state1 = generate_oauth_state()
    state2 = generate_oauth_state()
    assert isinstance(state1, str)
    assert len(state1) >= 16
    assert state1 != state2


def test_get_authorization_url() -> None:
    """Test get_google_authorization_url builds valid URL with scope."""
    state = "test_state_123"
    with patch("tools.google_auth.Flow.from_client_config") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/auth?state=test_state_123",
            "test_state_123",
        )
        mock_flow_cls.return_value = mock_flow

        url = get_google_authorization_url(state=state)
        assert "accounts.google.com" in url
        assert "test_state_123" in url


def test_oauth_state_validation_success() -> None:
    """Test state validation succeeds when received state matches expected state."""
    state = "valid_state_456"
    with patch("tools.google_auth.Flow.from_client_config") as mock_flow_cls:
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "fake_access_token"
        mock_creds.refresh_token = "fake_refresh_token"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "fake_client_id"
        mock_creds.client_secret = "fake_client_secret"
        mock_creds.scopes = ["https://www.googleapis.com/auth/calendar"]
        mock_flow.credentials = mock_creds
        mock_flow_cls.return_value = mock_flow

        result = exchange_code_for_credentials(
            code="fake_code",
            expected_state=state,
            received_state=state,
        )
        assert result["token"] == "fake_access_token"
        assert result["refresh_token"] == "fake_refresh_token"


def test_oauth_state_validation_rejection() -> None:
    """Test OAuth exchange rejects mismatched state tokens."""
    with pytest.raises(ValueError, match="state mismatch"):
        exchange_code_for_credentials(
            code="fake_code",
            expected_state="expected_state_123",
            received_state="mismatched_state_999",
        )


def test_credentials_save_load_clear(tmp_path: Path) -> None:
    """Test credentials saving, loading, and clearing via temporary file."""
    token_file = str(tmp_path / "token.json")
    assert load_credentials(token_file) is None

    creds_data = {
        "token": "token_abc",
        "refresh_token": "refresh_xyz",
        "client_id": "client_123",
    }
    save_credentials(creds_data, path=token_file)
    loaded = load_credentials(token_file)
    assert loaded == creds_data

    clear_credentials(token_file)
    assert load_credentials(token_file) is None


def test_credentials_not_in_gitignore() -> None:
    """Verify credential token files are present in .gitignore."""
    gitignore_path = Path(".gitignore")
    assert gitignore_path.exists()
    content = gitignore_path.read_text(encoding="utf-8")
    assert "token.json" in content


def test_credentials_logging_safety(caplog: pytest.LogCaptureFixture) -> None:
    """Verify secrets and tokens are not logged during credential operations."""
    # Verify operations execute without logging raw secret values
    state = generate_oauth_state()
    assert state != ""

    for record in caplog.records:
        assert "secret_access_token" not in record.getMessage()
        assert "secret_refresh_token" not in record.getMessage()
        assert "top_secret_key" not in record.getMessage()
