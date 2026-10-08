from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.agreement_service import cohens_kappa
from tests.conftest import make_rubric_payload

# --- Pure Cohen's kappa ----------------------------------------------------------------


def test_kappa_known_example() -> None:
    # Po = 2/4; Pe = (2*1 + 1*1 + 1*2) / 16 = 5/16; kappa = (8/16 - 5/16) / (11/16) = 3/11
    result = cohens_kappa([5, 4, 3, 5], [5, 3, 3, 4])

    assert result.observed_agreement == pytest.approx(0.5)
    assert result.expected_agreement == pytest.approx(5 / 16)
    assert result.kappa == pytest.approx(3 / 11)


def test_kappa_textbook_example() -> None:
    # Classic 2x2 example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> kappa = 0.4
    a = [1] * 20 + [1] * 5 + [0] * 10 + [0] * 15
    b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15

    result = cohens_kappa(a, b)

    assert result.observed_agreement == pytest.approx(0.7)
    assert result.expected_agreement == pytest.approx(0.5)
    assert result.kappa == pytest.approx(0.4)


def test_kappa_perfect_agreement() -> None:
    assert cohens_kappa([1, 2, 3, 4], [1, 2, 3, 4]).kappa == pytest.approx(1.0)


def test_kappa_worse_than_chance_is_negative() -> None:
    assert cohens_kappa([1, 2, 1, 2], [2, 1, 2, 1]).kappa == pytest.approx(-1.0)


def test_kappa_is_undefined_when_expected_agreement_is_one() -> None:
    result = cohens_kappa([4, 4, 4], [4, 4, 4])

    assert result.observed_agreement == 1.0
    assert result.expected_agreement == 1.0
    assert result.kappa is None


@pytest.mark.parametrize(("a", "b"), [([1, 2], [1]), ([], [])])
def test_kappa_rejects_invalid_input(a: list[int], b: list[int]) -> None:
    with pytest.raises(ValueError):
        cohens_kappa(a, b)


# --- Agreement endpoint ----------------------------------------------------------------


def test_fewer_than_two_evaluations_returns_409(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    url = f"/submissions/{submission['id']}/agreement"
    assert client.get(url).status_code == 409

    score([5, 4, 3])
    response = client.get(url)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INSUFFICIENT_EVALUATIONS"
    assert "At least two evaluations" in response.json()["detail"]["message"]


def test_agreement_for_unknown_submission_returns_404(client: TestClient) -> None:
    assert client.get("/submissions/42/agreement").status_code == 404


def test_two_raters_known_kappa(client: TestClient, submission: dict[str, Any], score: Any) -> None:
    four = client.post(
        "/rubrics", json=make_rubric_payload(("Correctness", "Relevance", "Clarity", "Safety"))
    ).json()
    score([5, 4, 3, 5], rater="rater-001", rubric_data=four)
    score([5, 3, 3, 4], rater="rater-002", rubric_data=four)

    response = client.get(f"/submissions/{submission['id']}/agreement")

    assert response.status_code == 200
    body = response.json()
    assert body["rubric_id"] == four["id"]
    assert (body["rater_count"], body["criterion_count"]) == (2, 4)
    [pair] = body["pairwise"]
    assert (pair["rater_a"]["external_id"], pair["rater_b"]["external_id"]) == (
        "rater-001",
        "rater-002",
    )
    assert pair["scores_a"] == [5, 4, 3, 5]
    assert pair["scores_b"] == [5, 3, 3, 4]
    assert pair["compared_criteria"] == 4
    assert pair["observed_agreement"] == 0.5
    assert pair["expected_agreement"] == 0.3125
    assert pair["kappa"] == pytest.approx(3 / 11, abs=1e-4)
    assert body["mean_pairwise_kappa"] == pair["kappa"]
    assert "interpreted cautiously" in body["note"]


def test_three_raters_produce_pairwise_results(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    score([5, 4, 3], rater="rater-003")
    score([5, 4, 3], rater="rater-001")
    score([1, 2, 3], rater="rater-002")

    body = client.get(f"/submissions/{submission['id']}/agreement").json()

    assert body["rater_count"] == 3
    pairs = {
        (p["rater_a"]["external_id"], p["rater_b"]["external_id"]): p for p in body["pairwise"]
    }
    assert set(pairs) == {
        ("rater-001", "rater-002"),
        ("rater-001", "rater-003"),
        ("rater-002", "rater-003"),
    }
    assert pairs[("rater-001", "rater-003")]["kappa"] == 1.0
    assert pairs[("rater-001", "rater-002")]["observed_agreement"] == pytest.approx(1 / 3, abs=1e-4)
    expected_mean = sum(p["kappa"] for p in body["pairwise"]) / 3
    assert body["mean_pairwise_kappa"] == pytest.approx(expected_mean, abs=1e-4)


def test_undefined_kappa_is_reported_not_zeroed(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    score([4, 4, 4], rater="rater-001")
    score([4, 4, 4], rater="rater-002")

    body = client.get(f"/submissions/{submission['id']}/agreement").json()

    assert body["pairwise"][0]["kappa"] is None
    assert body["pairwise"][0]["observed_agreement"] == 1.0
    assert body["pairwise"][0]["kappa_note"]
    assert body["mean_pairwise_kappa"] is None


def test_multiple_rubrics_require_rubric_id(
    client: TestClient, submission: dict[str, Any], rubric: dict[str, Any], score: Any
) -> None:
    other = client.post("/rubrics", json=make_rubric_payload(("Safety", "Tone"))).json()
    score([5, 4, 3], rater="rater-001")
    score([4, 4, 3], rater="rater-002")
    score([2, 3], rater="rater-001", rubric_data=other)
    url = f"/submissions/{submission['id']}/agreement"

    unscoped = client.get(url)
    scoped = client.get(url, params={"rubric_id": rubric["id"]})
    single = client.get(url, params={"rubric_id": other["id"]})

    assert unscoped.status_code == 422
    assert unscoped.json()["detail"]["code"] == "RUBRIC_ID_REQUIRED"
    assert scoped.status_code == 200
    assert scoped.json()["rater_count"] == 2
    assert single.status_code == 409
