import pytest

from app.db.session import normalize_database_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("sqlite:///./eval.db", "sqlite:///./eval.db"),
    ],
)
def test_normalize_database_url(url: str, expected: str) -> None:
    assert normalize_database_url(url) == expected
