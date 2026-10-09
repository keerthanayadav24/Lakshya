"""Google OAuth 2.0 flow and local credential management for Lakshya."""

import os
import secrets
from typing import Any

from google_auth_oauthlib.flow import Flow

import db
from config import settings

# Narrowest scope required for Lakshya study planner
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

if os.environ.get("ENVIRONMENT", "development") != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"


def generate_oauth_state() -> str:
    """Generate a cryptographically random OAuth state token."""
    return secrets.token_urlsafe(32)


def get_google_authorization_url(
    state: str,
    redirect_uri: str | None = None,
) -> str:
    if redirect_uri is None:
        redirect_uri = settings.google_redirect_uri
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
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return str(auth_url)


def exchange_code_for_credentials(
    code: str,
    expected_state: str,
    received_state: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    if redirect_uri is None:
        redirect_uri = settings.google_redirect_uri
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
) -> None:
    """Save OAuth credentials securely in the database."""
    db.save_credentials(credentials)


def load_credentials() -> dict[str, Any] | None:
    """Load OAuth credentials from the database if present."""
    return db.load_credentials()


def clear_credentials() -> None:
    """Remove saved OAuth credentials from the database."""
    db.clear_credentials()
