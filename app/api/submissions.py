from fastapi import APIRouter, status

from app.api.errors import error_responses
from app.db.session import DbSession
from app.schemas.submissions import SubmissionCreate, SubmissionRead
from app.services import submission_service

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a model output",
    description=(
        "Store an LLM output for evaluation. `prompt`, `output` and `model_name` are required; "
        "`model_metadata` accepts any JSON object."
    ),
)
def create_submission(payload: SubmissionCreate, db: DbSession) -> SubmissionRead:
    submission = submission_service.create_submission(db, payload)
    return submission_service.to_submission_read(submission)


@router.get(
    "/{submission_id}",
    summary="Get a submission",
    description="A submission with its model metadata, reference answer and every evaluation.",
    responses=error_responses(status.HTTP_404_NOT_FOUND),
)
def get_submission(submission_id: int, db: DbSession) -> SubmissionRead:
    submission = submission_service.get_submission(db, submission_id, with_evaluations=True)
    return submission_service.to_submission_read(submission)
