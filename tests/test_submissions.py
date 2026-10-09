from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import SUBMISSION_PAYLOAD, is_utc_iso8601


def test_create_submission(client: TestClient) -> None:
    response = client.post("/submissions", json=SUBMISSION_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["model_metadata"] == SUBMISSION_PAYLOAD["model_metadata"]
    assert body["reference_answer"] == SUBMISSION_PAYLOAD["reference_answer"]
    assert body["evaluations"] == []
    assert is_utc_iso8601(body["created_at"])


def test_optional_fields_may_be_omitted(client: TestClient) -> None:
    response = client.post(
        "/submissions", json={"prompt": "Hi", "output": "Hello!", "model_name": "m"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["model_version"] is None
    assert body["model_metadata"] is None
    assert body["reference_answer"] is None


def test_required_fields_are_enforced(client: TestClient) -> None:
    response = client.post("/submissions", json={"prompt": "Hi", "output": ""})

    assert response.status_code == 422
    errors = {tuple(e["loc"]) for e in response.json()["detail"]}
    assert ("body", "output") in errors
    assert ("body", "model_name") in errors


def test_get_submission_includes_evaluations(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    assert score([5, 4, 3]).status_code == 201

    response = client.get(f"/submissions/{submission['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["prompt"] == SUBMISSION_PAYLOAD["prompt"]
    assert len(body["evaluations"]) == 1
    assert body["evaluations"][0]["rater"]["external_id"] == "rater-001"


def test_get_unknown_submission_returns_404(client: TestClient) -> None:
    response = client.get("/submissions/12345")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SUBMISSION_NOT_FOUND"


def test_list_submissions_newest_first_with_counts(
    client: TestClient, submission: dict[str, Any], score: Any
) -> None:
    score([5, 4, 3])  # scores the fixture submission (id 1)
    client.post("/submissions", json={**SUBMISSION_PAYLOAD, "prompt": "Why? " * 100})

    response = client.get("/submissions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    newest, oldest = body["items"]
    assert (newest["id"], newest["evaluation_count"]) == (2, 0)
    assert (oldest["id"], oldest["evaluation_count"]) == (submission["id"], 1)
    assert oldest["prompt_preview"] == SUBMISSION_PAYLOAD["prompt"]
    assert len(newest["prompt_preview"]) <= 120
    assert newest["prompt_preview"].endswith("…")
    assert "output" not in newest


def test_list_submissions_paginates(client: TestClient) -> None:
    for _ in range(3):
        client.post("/submissions", json=SUBMISSION_PAYLOAD)

    body = client.get("/submissions", params={"limit": 1, "offset": 1}).json()

    assert body["total"] == 3
    assert [s["id"] for s in body["items"]] == [2]
    assert client.get("/submissions", params={"limit": 0}).status_code == 422
