"""Main FastAPI application entrypoint for Lakshya."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.agent_routes import router as agent_router
from db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """App lifespan context manager for startup database initialization."""
    init_db()
    yield


app = FastAPI(title="Lakshya API", lifespan=lifespan)

# Include agent proposal API routes
app.include_router(agent_router)

# Mount static folder for serving CSS, JS, and static assets
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint returning status ok."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def read_root() -> HTMLResponse:
    """Serve the basic semantic HTML frontend placeholder."""
    index_path = Path("static/index.html")
    content = index_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)
