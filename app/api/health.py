from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import DbSession

router = APIRouter(tags=["Health"])


@router.get(
    "/health", summary="Health check", description="Liveness plus a `SELECT 1` database check."
)
def health(db: DbSession) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error"})
    return JSONResponse(content={"status": "ok", "database": "ok"})
