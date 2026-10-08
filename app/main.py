from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import __version__
from app.api import analysis, health, rubrics, scores, submissions
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, log_requests
from app.db.base import Base
from app.db.session import create_db_engine

DESCRIPTION = """
Create evaluation rubrics, submit AI/LLM outputs, score them against rubrics with
multiple human raters, and measure inter-rater agreement (Cohen's kappa).

Business-rule errors use one format:
`{"detail": {"code": "...", "message": "...", "field": "..."}}`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url, echo=settings.sql_echo)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # For a zero-configuration assessment the schema is created on startup;
        # a production deployment would use migrations (e.g. Alembic) instead.
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="AI Model Evaluation & Rubric Management API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    register_error_handlers(app)
    app.middleware("http")(log_requests)
    for module in (health, rubrics, submissions, scores, analysis):
        app.include_router(module.router)
    return app


app = create_app()
