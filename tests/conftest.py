from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ANCHOR_LABELS = ["Very poor", "Poor", "Acceptable", "Good", "Excellent"]


def make_rubric_payload(
    criteria: tuple[str, ...] = ("Correctness", "Relevance", "Clarity"),
    *,
    scale_min: int = 1,
    scale_max: int = 5,
    weights: tuple[float, ...] | None = None,
) -> dict[str, Any]:
    weights = weights or tuple(1.0 for _ in criteria)
    return {
        "name": "General Response Quality",
        "description": "Evaluates correctness, relevance and clarity.",
        "scale_min": scale_min,
        "scale_max": scale_max,
        "criteria": [
            {
                "name": name,
                "description": f"How good is the response's {name.lower()}?",
                "weight": weight,
                "anchors": [
                    {
                        "score": score,
                        "label": ANCHOR_LABELS[(score - scale_min) % len(ANCHOR_LABELS)],
                        "description": f"{name} at level {score}.",
                    }
                    for score in range(scale_min, scale_max + 1)
                ],
            }
            for name, weight in zip(criteria, weights, strict=True)
        ],
    }


SUBMISSION_PAYLOAD: dict[str, Any] = {
    "prompt": "Explain why idempotency matters in payment APIs.",
    "output": "Idempotency prevents repeated requests from charging a customer twice...",
    "model_name": "example-model",
    "model_version": "v1",
    "model_metadata": {"temperature": 0.2, "provider": "example", "run_id": "abc123"},
    "reference_answer": "A strong answer discusses duplicate requests, retries and keys.",
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client backed by a fresh SQLite file per test; the developer database is never touched."""
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def rubric(client: TestClient) -> dict[str, Any]:
    response = client.post("/rubrics", json=make_rubric_payload())
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def submission(client: TestClient) -> dict[str, Any]:
    response = client.post("/submissions", json=SUBMISSION_PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


ScoreFn = Callable[..., Any]


@pytest.fixture
def score(client: TestClient, rubric: dict[str, Any], submission: dict[str, Any]) -> ScoreFn:
    """Post an evaluation; `scores` are given in rubric criterion order."""

    def _score(
        scores: list[int],
        *,
        rater: str = "rater-001",
        overall: int = 4,
        rubric_data: dict[str, Any] | None = None,
        submission_id: int | None = None,
    ) -> Any:
        target_rubric = rubric_data or rubric
        return client.post(
            f"/submissions/{submission_id or submission['id']}/scores",
            json={
                "rubric_id": target_rubric["id"],
                "rater": {"external_id": rater, "name": f"Evaluator {rater}"},
                "criterion_scores": [
                    {"criterion_id": c["id"], "score": s, "comment": None}
                    for c, s in zip(target_rubric["criteria"], scores, strict=True)
                ],
                "overall_score": overall,
                "comments": "Test evaluation.",
            },
        )

    return _score


def is_utc_iso8601(value: str) -> bool:
    return datetime.fromisoformat(value).utcoffset() == timedelta(0)
