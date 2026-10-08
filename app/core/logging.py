"""Structured (JSON) request logging.

Only request metadata is logged. Prompts, model outputs, reference answers and
evaluator comments are deliberately never logged because evaluation data may be
sensitive.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import Request, Response

request_logger = logging.getLogger("app.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level.upper())
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        app_logger.addHandler(handler)
    app_logger.propagate = False


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # Log the route template (e.g. /submissions/{submission_id}) rather than the raw path.
        route = request.scope.get("route")
        request_logger.info(
            "http_request",
            extra={
                "fields": {
                    "method": request.method,
                    "route": getattr(route, "path", request.url.path),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            },
        )
