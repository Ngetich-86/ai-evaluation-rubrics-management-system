"""Serves the static web interface (frontend/) from the same origin as the API, so no CORS
configuration is needed."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

router = APIRouter(include_in_schema=False)


@router.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
