from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.errors import error_responses
from app.db.session import DbSession
from app.schemas.evaluations import EvaluationCreate, EvaluationRead
from app.services import evaluation_service

router = APIRouter(prefix="/submissions/{submission_id}/scores", tags=["Scores"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Score a submission",
    description=(
        "Record one rater's evaluation against a rubric. Every rubric criterion must be scored "
        "exactly once, with scores and `overall_score` inside the rubric scale. Raters are matched "
        "by `external_id` and created on first use. A rater can evaluate a submission only once "
        "per rubric; a repeat returns 409 and never overwrites. The evaluation and its criterion "
        "scores are written in one transaction."
    ),
    responses=error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT, 422),
)
def create_score(submission_id: int, payload: EvaluationCreate, db: DbSession) -> EvaluationRead:
    evaluation = evaluation_service.create_evaluation(db, submission_id, payload)
    return evaluation_service.to_evaluation_read(evaluation)


@router.get(
    "",
    summary="List a submission's scores",
    description="All evaluations for a submission with rater, rubric and criterion scores.",
    responses=error_responses(status.HTTP_404_NOT_FOUND),
)
def list_scores(
    submission_id: int,
    db: DbSession,
    rubric_id: Annotated[
        int | None, Query(gt=0, description="Only this rubric's evaluations.")
    ] = None,
) -> list[EvaluationRead]:
    evaluations = evaluation_service.list_evaluations(db, submission_id, rubric_id=rubric_id)
    return [evaluation_service.to_evaluation_read(e) for e in evaluations]
