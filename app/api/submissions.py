from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.errors import error_responses
from app.db.session import DbSession
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.schemas.submissions import SubmissionCreate, SubmissionList, SubmissionRead
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
    "",
    summary="List submissions",
    description=(
        "Newest first, with limit/offset paging. Each entry has a prompt preview and the number "
        "of evaluations; fetch a submission by id for its full text and scores."
    ),
)
def list_submissions(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubmissionList:
    items, total = submission_service.list_submissions(db, limit=limit, offset=offset)
    return SubmissionList(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{submission_id}",
    summary="Get a submission",
    description="A submission with its model metadata, reference answer and every evaluation.",
    responses=error_responses(status.HTTP_404_NOT_FOUND),
)
def get_submission(submission_id: int, db: DbSession) -> SubmissionRead:
    submission = submission_service.get_submission(db, submission_id, with_evaluations=True)
    return submission_service.to_submission_read(submission)
