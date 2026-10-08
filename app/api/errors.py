from typing import Any

from app.schemas.common import ErrorResponse


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI documentation for the structured error responses an endpoint can return."""
    return {code: {"model": ErrorResponse} for code in status_codes}
