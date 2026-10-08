from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.db.models import Submission
from app.schemas.submissions import SubmissionCreate, SubmissionRead
from app.services.evaluation_service import EVALUATION_LOAD_OPTIONS, to_evaluation_read


def create_submission(db: Session, payload: SubmissionCreate) -> Submission:
    submission = Submission(**payload.model_dump())
    db.add(submission)
    db.commit()
    return submission


def get_submission(
    db: Session, submission_id: int, *, with_evaluations: bool = False
) -> Submission:
    stmt = select(Submission).where(Submission.id == submission_id)
    if with_evaluations:
        stmt = stmt.options(
            *(selectinload(Submission.evaluations).options(o) for o in EVALUATION_LOAD_OPTIONS)
        )
    submission = db.scalar(stmt)
    if submission is None:
        raise NotFoundError(
            f"Submission {submission_id} was not found.", code="SUBMISSION_NOT_FOUND"
        )
    return submission


def to_submission_read(submission: Submission) -> SubmissionRead:
    return SubmissionRead(
        id=submission.id,
        prompt=submission.prompt,
        output=submission.output,
        model_name=submission.model_name,
        model_version=submission.model_version,
        model_metadata=submission.model_metadata,
        reference_answer=submission.reference_answer,
        created_at=submission.created_at,
        evaluations=[to_evaluation_read(e) for e in submission.evaluations],
    )
