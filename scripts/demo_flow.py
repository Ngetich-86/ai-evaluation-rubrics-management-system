"""Run the full evaluation workflow against a running API.

    uvicorn app.main:app --reload          # in one terminal
    python scripts/demo_flow.py            # in another (requires httpx: pip install -e ".[dev]")

Pass a different base URL as the first argument if needed.
"""

import json
import sys
from typing import Any

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

ANCHORS = {
    1: ("Very poor", "Fails the criterion."),
    2: ("Weak", "Substantial problems."),
    3: ("Acceptable", "Meets the criterion with minor issues."),
    4: ("Strong", "Very minor shortcomings."),
    5: ("Excellent", "Fully meets the criterion."),
}

RUBRIC = {
    "name": "General Response Quality",
    "description": "Evaluates correctness, relevance and clarity.",
    "scale_min": 1,
    "scale_max": 5,
    "criteria": [
        {
            "name": name,
            "description": description,
            "weight": weight,
            "anchors": [
                {"score": s, "label": label, "description": text}
                for s, (label, text) in ANCHORS.items()
            ],
        }
        for name, description, weight in [
            ("Correctness", "How factually and logically correct is the response?", 2.0),
            ("Relevance", "Does the response address the prompt?", 1.0),
            ("Clarity", "Is the response clear and well organised?", 1.0),
        ]
    ],
}

SUBMISSION = {
    "prompt": "Explain why idempotency matters in payment APIs.",
    "output": "Idempotency prevents repeated requests from charging a customer twice...",
    "model_name": "example-model",
    "model_version": "v1",
    "model_metadata": {"temperature": 0.2},
    "reference_answer": "A strong answer discusses duplicate requests, retries and keys.",
}


def show(title: str, response: httpx.Response) -> Any:
    print(
        f"\n=== {title}: {response.request.method} {response.request.url.path} "
        f"-> {response.status_code}"
    )
    body = response.json()
    print(json.dumps(body, indent=2)[:1500])
    response.raise_for_status()
    return body


def evaluation(rubric: dict[str, Any], rater: str, scores: list[int], overall: int) -> dict:
    return {
        "rubric_id": rubric["id"],
        "rater": {"external_id": rater, "name": rater.replace("-", " ").title()},
        "criterion_scores": [
            {"criterion_id": c["id"], "score": s}
            for c, s in zip(rubric["criteria"], scores, strict=True)
        ],
        "overall_score": overall,
        "comments": f"Demo evaluation by {rater}.",
    }


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        show("Health", client.get("/health"))
        rubric = show("Create rubric", client.post("/rubrics", json=RUBRIC))
        submission = show("Create submission", client.post("/submissions", json=SUBMISSION))
        scores_url = f"/submissions/{submission['id']}/scores"
        show(
            "Rater A scores",
            client.post(scores_url, json=evaluation(rubric, "rater-a", [5, 4, 4], 4)),
        )
        show(
            "Rater B scores",
            client.post(scores_url, json=evaluation(rubric, "rater-b", [4, 4, 3], 4)),
        )
        show("List scores", client.get(scores_url))
        show("Agreement", client.get(f"/submissions/{submission['id']}/agreement"))


if __name__ == "__main__":
    main()
