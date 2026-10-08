from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import CriterionScore, Evaluation, Rater
from app.services import evaluation_service
from tests.conftest import make_rubric_payload


def _count(client: TestClient, model: type) -> int:
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        return session.scalar(select(func.count()).select_from(model))


def _error(response: Any) -> dict[str, Any]:
    return response.json()["detail"]


def test_valid_evaluation(client: TestClient, rubric: dict[str, Any], score: Any) -> None:
    response = score([5, 4, 3], overall=4)

    assert response.status_code == 201
    body = response.json()
    assert body["rubric"]["id"] == rubric["id"]
    assert body["rater"]["external_id"] == "rater-001"
    assert body["overall_score"] == 4
    assert [cs["score"] for cs in body["criterion_scores"]] == [5, 4, 3]
    assert [cs["criterion_name"] for cs in body["criterion_scores"]] == [
        "Correctness",
        "Relevance",
        "Clarity",
    ]
    assert body["derived"]["mean_criterion_score"] == 4.0


def test_weighted_mean_is_derived_separately_from_overall_score(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    weighted = client.post("/rubrics", json=make_rubric_payload(weights=(3.0, 1.0, 1.0))).json()

    response = score([5, 1, 1], overall=2, rubric_data=weighted)

    assert response.status_code == 201
    body = response.json()
    assert body["overall_score"] == 2
    assert body["derived"]["mean_criterion_score"] == pytest.approx(7 / 3, abs=1e-4)
    assert body["derived"]["weighted_mean_criterion_score"] == pytest.approx(17 / 5)


def test_list_scores_with_rubric_filter(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    other = client.post("/rubrics", json=make_rubric_payload(("Safety",))).json()
    score([5, 4, 3], rater="rater-001")
    score([4, 4, 4], rater="rater-002")
    score([2], rater="rater-001", rubric_data=other)

    all_scores = client.get(f"/submissions/{submission['id']}/scores").json()
    filtered = client.get(
        f"/submissions/{submission['id']}/scores", params={"rubric_id": other["id"]}
    ).json()

    assert len(all_scores) == 3
    assert {e["rater"]["name"] for e in all_scores} == {
        "Evaluator rater-001",
        "Evaluator rater-002",
    }
    assert [e["rubric"]["id"] for e in filtered] == [other["id"]]


def test_list_scores_for_unknown_submission_returns_404(client: TestClient) -> None:
    assert client.get("/submissions/99/scores").status_code == 404


def test_unknown_submission_returns_404(score: Any) -> None:
    response = score([5, 4, 3], submission_id=999)

    assert response.status_code == 404
    assert _error(response)["code"] == "SUBMISSION_NOT_FOUND"


def test_unknown_rubric_returns_404(client: TestClient, rubric: dict[str, Any], score: Any) -> None:
    response = score([5, 4, 3], rubric_data={**rubric, "id": 999})

    assert response.status_code == 404
    assert _error(response) == {
        "code": "RUBRIC_NOT_FOUND",
        "message": "Rubric 999 was not found.",
        "field": "rubric_id",
    }


def test_criterion_from_another_rubric_is_rejected(
    client: TestClient, rubric: dict[str, Any], score: Any
) -> None:
    other = client.post("/rubrics", json=make_rubric_payload()).json()
    mixed = {**rubric, "criteria": [*rubric["criteria"][:2], other["criteria"][2]]}

    response = score([5, 4, 3], rubric_data=mixed)

    assert response.status_code == 422
    assert _error(response)["code"] == "CRITERION_NOT_IN_RUBRIC"
    assert _error(response)["field"] == "criterion_scores[2].criterion_id"


def test_out_of_range_criterion_score_is_rejected(score: Any) -> None:
    response = score([5, 6, 3])

    assert response.status_code == 422
    assert _error(response) == {
        "code": "INVALID_CRITERION_SCORE",
        "message": "Score 6 is outside rubric scale 1-5.",
        "field": "criterion_scores[1].score",
    }


def test_out_of_range_overall_score_is_rejected(score: Any) -> None:
    response = score([5, 4, 3], overall=0)

    assert response.status_code == 422
    assert _error(response)["code"] == "INVALID_OVERALL_SCORE"


def test_missing_criterion_score_is_rejected(rubric: dict[str, Any], score: Any) -> None:
    partial = {**rubric, "criteria": rubric["criteria"][:2]}

    response = score([5, 4], rubric_data=partial)

    assert response.status_code == 422
    assert _error(response)["code"] == "MISSING_CRITERION_SCORES"
    assert "Clarity" in _error(response)["message"]


def test_duplicate_criterion_in_payload_is_rejected(rubric: dict[str, Any], score: Any) -> None:
    repeated = {**rubric, "criteria": [*rubric["criteria"], rubric["criteria"][0]]}

    response = score([5, 4, 3, 2], rubric_data=repeated)

    assert response.status_code == 422
    assert _error(response)["code"] == "DUPLICATE_CRITERION_SCORE"


@pytest.mark.parametrize("bad_score", ["4", 4.5, True])
def test_non_integer_scores_are_rejected(score: Any, bad_score: Any) -> None:
    assert score([5, bad_score, 3]).status_code == 422


def test_invalid_rater_identity_is_rejected(
    client: TestClient, rubric: dict[str, Any], submission: dict[str, Any]
) -> None:
    response = client.post(
        f"/submissions/{submission['id']}/scores",
        json={
            "rubric_id": rubric["id"],
            "rater": {"external_id": "has spaces!", "name": ""},
            "criterion_scores": [{"criterion_id": c["id"], "score": 3} for c in rubric["criteria"]],
            "overall_score": 3,
        },
    )

    assert response.status_code == 422
    assert {tuple(e["loc"][-2:]) for e in response.json()["detail"]} == {
        ("rater", "external_id"),
        ("rater", "name"),
    }


def test_duplicate_evaluation_returns_409_and_keeps_original(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    assert score([5, 4, 3], overall=4).status_code == 201

    response = score([1, 1, 1], overall=1)

    assert response.status_code == 409
    assert _error(response)["code"] == "DUPLICATE_EVALUATION"
    stored = client.get(f"/submissions/{submission['id']}/scores").json()
    assert len(stored) == 1
    assert [cs["score"] for cs in stored[0]["criterion_scores"]] == [5, 4, 3]


def test_same_rater_may_score_other_submissions(client: TestClient, score: Any) -> None:
    other = client.post(
        "/submissions", json={"prompt": "p", "output": "o", "model_name": "m"}
    ).json()

    first = score([5, 4, 3]).json()
    second = score([3, 3, 3], submission_id=other["id"]).json()

    assert first["rater"]["id"] == second["rater"]["id"]
    assert _count(client, Rater) == 1


def test_rejected_evaluation_persists_nothing(client: TestClient, score: Any) -> None:
    assert score([5, 6, 3], rater="new-rater").status_code == 422

    assert _count(client, Rater) == 0
    assert _count(client, Evaluation) == 0
    assert _count(client, CriterionScore) == 0


def test_database_constraint_blocks_concurrent_duplicate_atomically(
    client: TestClient, score: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a race: the pre-check misses, so the unique constraint must reject the insert."""
    assert score([5, 4, 3]).status_code == 201
    monkeypatch.setattr(evaluation_service, "_find_existing_evaluation", lambda *_: None)

    response = score([1, 1, 1])

    assert response.status_code == 409
    assert _error(response)["code"] == "DUPLICATE_EVALUATION"
    assert _count(client, Evaluation) == 1
    assert _count(client, CriterionScore) == 3
