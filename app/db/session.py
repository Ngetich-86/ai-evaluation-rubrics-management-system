from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite ignores foreign keys (and therefore ON DELETE CASCADE) unless enabled per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def normalize_database_url(database_url: str) -> str:
    """Use the psycopg 3 driver for bare PostgreSQL URLs.

    Hosting providers such as Render supply `postgresql://` (or legacy `postgres://`) URLs, which
    SQLAlchemy would otherwise map to the psycopg2 driver. URLs naming a driver are left unchanged.
    """
    for prefix in ("postgres://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    database_url = normalize_database_url(database_url)
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool.
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, echo=echo, connect_args=connect_args, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def get_db(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session. Anything not explicitly committed is rolled back on close."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
