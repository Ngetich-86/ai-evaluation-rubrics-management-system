from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.errors import error_responses
from app.db.session import DbSession
from app.schemas.analysis import AgreementRead
from app.services import agreement_service

router = APIRouter(prefix="/submissions/{submission_id}", tags=["Analysis"])


@router.get(
    "/agreement",
    summary="Inter-rater agreement",
    description=(
        "Pairwise Cohen's kappa between every pair of raters who scored this submission with the "
        "same rubric, using rubric criteria as the rated units. Needs at least two evaluations "
        "(409 otherwise). If the submission was scored with more than one rubric, `rubric_id` is "
        "required (422 otherwise)."
    ),
    responses=error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT, 422),
)
def get_agreement(
    submission_id: int,
    db: DbSession,
    rubric_id: Annotated[int | None, Query(gt=0)] = None,
) -> AgreementRead:
    return agreement_service.compute_submission_agreement(db, submission_id, rubric_id)
