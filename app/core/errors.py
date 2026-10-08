"""Domain errors and the handler that renders them as structured API responses.

Every business-rule failure is returned as:

    {"detail": {"code": "...", "message": "...", "field": "..." | null}}
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.field = field

    def to_detail(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "field": self.field}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CONFLICT"


class BusinessRuleError(AppError):
    """A syntactically valid request that violates a domain rule."""

    status_code = 422
    default_code = "VALIDATION_ERROR"


async def _handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_detail()})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
