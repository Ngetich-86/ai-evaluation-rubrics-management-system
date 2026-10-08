"""Compatibility entry point so `uvicorn main:app` also works.

The application lives in the `app` package; prefer `uvicorn app.main:app --reload`.
"""

from app.main import app

__all__ = ["app"]
