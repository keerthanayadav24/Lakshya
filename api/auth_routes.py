"""FastAPI routes for Google OAuth 2.0 flow."""

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from tools.google_auth import (
    exchange_code_for_credentials,
    generate_oauth_state,
    get_google_authorization_url,
    save_credentials,
)

router = APIRouter(prefix="/oauth", tags=["Auth"])


@router.get("/start")
async def oauth_start() -> RedirectResponse:
    """Start the Google OAuth 2.0 authorization flow."""
    try:
        state = generate_oauth_state()
        auth_url = get_google_authorization_url(state=state)
        
        redirect = RedirectResponse(url=auth_url)
        redirect.set_cookie(
            key="oauth_state",
            value=state,
            httponly=True,
            max_age=600,  # 10 minutes
            samesite="lax",
            secure=False,  # Localhost is HTTP
        )
        return redirect
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to initialize OAuth flow.")


@router.get("/callback")
async def oauth_callback(
    request: Request,
    oauth_state: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Handle the OAuth 2.0 callback from Google."""
    code = request.query_params.get("code")
    received_state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        raise HTTPException(
            status_code=400, detail="OAuth authorization denied or failed."
        )

    if not code or not received_state:
        raise HTTPException(
            status_code=400, detail="Missing authorization code or state."
        )

    if not oauth_state:
        raise HTTPException(
            status_code=400, detail="OAuth state cookie missing or expired."
        )

    try:
        credentials = exchange_code_for_credentials(
            code=code,
            expected_state=oauth_state,
            received_state=received_state,
        )
        save_credentials(credentials)
        
        content = (
            "<html>\n"
            "    <head><title>Authentication Successful</title></head>\n"
            "    <body style=\"font-family: sans-serif; text-align: center; "
            "margin-top: 50px;\">\n"
            "        <h1>Authentication Successful</h1>\n"
            "        <p>Google Calendar has been linked successfully.</p>\n"
            "        <p>You may now close this window and "
            "return to the dashboard.</p>\n"
            "    </body>\n"
            "</html>"
        )
        return HTMLResponse(content=content, status_code=200)
    except ValueError as e:
        import logging
        logging.getLogger(__name__).error(
            f"OAuth state mismatch: {type(e).__name__} - {e}"
        )
        raise HTTPException(status_code=400, detail="OAuth state validation failed.")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            f"OAuth exchange failed: {type(e).__name__} - {e}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to exchange authorization code."
        )
