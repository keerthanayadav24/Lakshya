"""Google OAuth 2.0 flow and local credential management for Lakshya."""

import json
import os
import secrets
from typing import Any

from google_auth_oauthlib.flow import Flow

from config import settings

# Narrowest scope required for Lakshya study planner
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def generate_oauth_state() -> str:
    """Generate a cryptographically random OAuth state token."""
    return secrets.token_urlsafe(32)


def get_google_authorization_url(
    state: str,
    redirect_uri: str = "http://localhost:8000/oauth/callback",
) -> str:
    """Generate Google OAuth authorization URL for user consent."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=CALENDAR_SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(prompt="consent")
    return str(auth_url)


def exchange_code_for_credentials(
    code: str,
    expected_state: str,
    received_state: str,
    redirect_uri: str = "http://localhost:8000/oauth/callback",
) -> dict[str, Any]:
    """Exchange authorization code for credentials after validating state token."""
    if not received_state or received_state != expected_state:
        raise ValueError("OAuth state validation failed: state mismatch")

    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=CALENDAR_SCOPES,
        state=received_state,
    )
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)

    credentials = flow.credentials
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def save_credentials(
    credentials: dict[str, Any],
    path: str = "token.json",
) -> None:
    """Save OAuth credentials to a local JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)


def load_credentials(
    path: str = "token.json",
) -> dict[str, Any] | None:
    """Load OAuth credentials from local JSON file if present."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def clear_credentials(
    path: str = "token.json",
) -> None:
    """Remove local saved OAuth credentials file."""
    if os.path.exists(path):
        os.remove(path)
