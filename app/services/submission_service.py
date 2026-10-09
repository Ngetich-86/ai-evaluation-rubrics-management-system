from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.db.models import Evaluation, Submission
from app.schemas.submissions import SubmissionCreate, SubmissionRead, SubmissionSummary
from app.services.evaluation_service import EVALUATION_LOAD_OPTIONS, to_evaluation_read

PROMPT_PREVIEW_LENGTH = 120


def create_submission(db: Session, payload: SubmissionCreate) -> Submission:
    submission = Submission(**payload.model_dump())
    db.add(submission)
    db.commit()
    return submission


def list_submissions(
    db: Session, *, limit: int, offset: int
) -> tuple[list[SubmissionSummary], int]:
    """Newest submissions first, each with its number of evaluations."""
    total = db.scalar(select(func.count()).select_from(Submission)) or 0
    evaluation_count = (
        select(func.count(Evaluation.id))
        .where(Evaluation.submission_id == Submission.id)
        .correlate(Submission)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Submission, evaluation_count)
        .order_by(Submission.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_to_summary(submission, count) for submission, count in rows], total


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


def _to_summary(submission: Submission, evaluation_count: int) -> SubmissionSummary:
    prompt = submission.prompt
    if len(prompt) > PROMPT_PREVIEW_LENGTH:
        prompt = prompt[: PROMPT_PREVIEW_LENGTH - 1].rstrip() + "…"
    return SubmissionSummary(
        id=submission.id,
        model_name=submission.model_name,
        model_version=submission.model_version,
        prompt_preview=prompt,
        evaluation_count=evaluation_count,
        created_at=submission.created_at,
    )
