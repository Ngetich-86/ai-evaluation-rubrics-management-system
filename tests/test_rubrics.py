from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import is_utc_iso8601, make_rubric_payload


def test_create_rubric_returns_complete_rubric(client: TestClient) -> None:
    response = client.post("/rubrics", json=make_rubric_payload(weights=(2.0, 1.0, 0.5)))

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert (body["scale_min"], body["scale_max"]) == (1, 5)
    assert [c["name"] for c in body["criteria"]] == ["Correctness", "Relevance", "Clarity"]
    assert [c["weight"] for c in body["criteria"]] == [2.0, 1.0, 0.5]
    assert [c["position"] for c in body["criteria"]] == [0, 1, 2]
    assert [a["score"] for a in body["criteria"][0]["anchors"]] == [1, 2, 3, 4, 5]
    assert body["criteria"][0]["anchors"][4]["label"] == "Excellent"
    assert is_utc_iso8601(body["created_at"])


def test_weight_defaults_to_one(client: TestClient) -> None:
    payload = make_rubric_payload()
    del payload["criteria"][0]["weight"]

    response = client.post("/rubrics", json=payload)

    assert response.status_code == 201
    assert response.json()["criteria"][0]["weight"] == 1.0


def test_get_rubric_round_trips(client: TestClient, rubric: dict[str, Any]) -> None:
    response = client.get(f"/rubrics/{rubric['id']}")

    assert response.status_code == 200
    assert response.json() == rubric


def test_get_unknown_rubric_returns_structured_404(client: TestClient) -> None:
    response = client.get("/rubrics/999")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RUBRIC_NOT_FOUND"


def test_list_rubrics_paginates(client: TestClient) -> None:
    for _ in range(3):
        client.post("/rubrics", json=make_rubric_payload())

    response = client.get("/rubrics", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert (body["limit"], body["offset"]) == (2, 1)
    assert [r["id"] for r in body["items"]] == [2, 3]


def _drop_anchor(payload: dict[str, Any]) -> None:
    payload["criteria"][1]["anchors"].pop(2)


def _duplicate_anchor(payload: dict[str, Any]) -> None:
    payload["criteria"][0]["anchors"][1]["score"] = 1


def _out_of_range_anchor(payload: dict[str, Any]) -> None:
    payload["criteria"][0]["anchors"].append({"score": 6, "label": "Beyond", "description": None})


def _duplicate_criterion(payload: dict[str, Any]) -> None:
    payload["criteria"][2]["name"] = "correctness"


def _empty_criterion_name(payload: dict[str, Any]) -> None:
    payload["criteria"][0]["name"] = "   "


def _inverted_scale(payload: dict[str, Any]) -> None:
    payload["scale_min"], payload["scale_max"] = 5, 1


def _non_positive_weight(payload: dict[str, Any]) -> None:
    payload["criteria"][0]["weight"] = 0


def _no_criteria(payload: dict[str, Any]) -> None:
    payload["criteria"] = []


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (_drop_anchor, "missing [3]"),
        (_duplicate_anchor, "duplicate anchor scores [1]"),
        (_out_of_range_anchor, "outside the rubric scale 1-5"),
        (_duplicate_criterion, "duplicate criterion name"),
        (_empty_criterion_name, "at least 1 character"),
        (_inverted_scale, "must be less than scale_max"),
        (_non_positive_weight, "greater than 0"),
        (_no_criteria, "at least 1 item"),
    ],
)
def test_invalid_rubrics_are_rejected(
    client: TestClient, mutate: Any, expected_message: str
) -> None:
    payload = make_rubric_payload()
    mutate(payload)

    response = client.post("/rubrics", json=payload)

    assert response.status_code == 422
    assert expected_message in response.text
    assert client.get("/rubrics").json()["total"] == 0
