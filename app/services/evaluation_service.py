"""Evaluation (scoring) business rules.

An evaluation and all of its criterion scores are created in a single transaction:
every rule is checked before anything is written, the rows are committed together,
and the database unique constraint is the backstop against concurrent duplicates.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.db.models import Criterion, CriterionScore, Evaluation, Rater, Rubric, Submission
from app.schemas.evaluations import (
    CriterionScoreRead,
    DerivedScores,
    EvaluationCreate,
    EvaluationRead,
    RaterIdentity,
    RaterRead,
)
from app.schemas.rubrics import RubricSummary
from app.services import rubric_service

DERIVED_SCORE_PRECISION = 4

EVALUATION_LOAD_OPTIONS = (
    selectinload(Evaluation.rater),
    selectinload(Evaluation.rubric),
    selectinload(Evaluation.criterion_scores).selectinload(CriterionScore.criterion),
)


def create_evaluation(db: Session, submission_id: int, payload: EvaluationCreate) -> Evaluation:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise NotFoundError(
            f"Submission {submission_id} was not found.", code="SUBMISSION_NOT_FOUND"
        )
    rubric = rubric_service.get_rubric(db, payload.rubric_id, field="rubric_id")
    criteria_by_id = _validate_scores(rubric, payload)

    rater = _get_or_create_rater(db, payload.rater)
    if _find_existing_evaluation(db, submission.id, rubric.id, rater.id) is not None:
        db.rollback()
        raise _duplicate_evaluation_error(rater.external_id, submission.id, rubric.id)

    evaluation = Evaluation(
        submission=submission,
        rubric=rubric,
        rater=rater,
        overall_score=payload.overall_score,
        comments=payload.comments,
        criterion_scores=[
            CriterionScore(
                criterion=criteria_by_id[item.criterion_id], score=item.score, comment=item.comment
            )
            for item in payload.criterion_scores
        ],
    )
    db.add(evaluation)
    try:
        db.commit()
    except IntegrityError as exc:
        # A concurrent request inserted the same submission/rubric/rater first.
        db.rollback()
        raise _duplicate_evaluation_error(rater.external_id, submission.id, rubric.id) from exc
    return evaluation


def list_evaluations(
    db: Session, submission_id: int, *, rubric_id: int | None = None
) -> list[Evaluation]:
    if db.get(Submission, submission_id) is None:
        raise NotFoundError(
            f"Submission {submission_id} was not found.", code="SUBMISSION_NOT_FOUND"
        )
    stmt = (
        select(Evaluation)
        .where(Evaluation.submission_id == submission_id)
        .order_by(Evaluation.id)
        .options(*EVALUATION_LOAD_OPTIONS)
    )
    if rubric_id is not None:
        if db.get(Rubric, rubric_id) is None:
            raise NotFoundError(
                f"Rubric {rubric_id} was not found.", code="RUBRIC_NOT_FOUND", field="rubric_id"
            )
        stmt = stmt.where(Evaluation.rubric_id == rubric_id)
    return list(db.scalars(stmt).all())


def to_evaluation_read(evaluation: Evaluation) -> EvaluationRead:
    scores = sorted(evaluation.criterion_scores, key=lambda cs: cs.criterion.position)
    total_weight = sum(cs.criterion.weight for cs in scores)
    return EvaluationRead(
        id=evaluation.id,
        submission_id=evaluation.submission_id,
        rubric=RubricSummary.model_validate(evaluation.rubric),
        rater=RaterRead.model_validate(evaluation.rater),
        overall_score=evaluation.overall_score,
        comments=evaluation.comments,
        criterion_scores=[
            CriterionScoreRead(
                id=cs.id,
                criterion_id=cs.criterion_id,
                criterion_name=cs.criterion.name,
                weight=cs.criterion.weight,
                score=cs.score,
                comment=cs.comment,
            )
            for cs in scores
        ],
        derived=DerivedScores(
            mean_criterion_score=round(
                sum(cs.score for cs in scores) / len(scores), DERIVED_SCORE_PRECISION
            ),
            weighted_mean_criterion_score=round(
                sum(cs.score * cs.criterion.weight for cs in scores) / total_weight,
                DERIVED_SCORE_PRECISION,
            ),
        ),
        created_at=evaluation.created_at,
    )


def _validate_scores(rubric: Rubric, payload: EvaluationCreate) -> dict[int, Criterion]:
    """Enforce complete, in-range scoring of exactly the rubric's criteria."""
    criteria_by_id = {criterion.id: criterion for criterion in rubric.criteria}
    scale = f"{rubric.scale_min}-{rubric.scale_max}"
    seen: set[int] = set()

    for index, item in enumerate(payload.criterion_scores):
        field = f"criterion_scores[{index}]"
        if item.criterion_id in seen:
            raise BusinessRuleError(
                f"Criterion {item.criterion_id} is scored more than once.",
                code="DUPLICATE_CRITERION_SCORE",
                field=f"{field}.criterion_id",
            )
        seen.add(item.criterion_id)
        if item.criterion_id not in criteria_by_id:
            raise BusinessRuleError(
                f"Criterion {item.criterion_id} does not belong to rubric {rubric.id}.",
                code="CRITERION_NOT_IN_RUBRIC",
                field=f"{field}.criterion_id",
            )
        if not rubric.scale_min <= item.score <= rubric.scale_max:
            raise BusinessRuleError(
                f"Score {item.score} is outside rubric scale {scale}.",
                code="INVALID_CRITERION_SCORE",
                field=f"{field}.score",
            )

    missing = [cid for cid in criteria_by_id if cid not in seen]
    if missing:
        names = ", ".join(f"{cid} ({criteria_by_id[cid].name})" for cid in missing)
        raise BusinessRuleError(
            f"Every rubric criterion must be scored; missing criteria: {names}.",
            code="MISSING_CRITERION_SCORES",
            field="criterion_scores",
        )
    if not rubric.scale_min <= payload.overall_score <= rubric.scale_max:
        raise BusinessRuleError(
            f"Overall score {payload.overall_score} is outside rubric scale {scale}.",
            code="INVALID_OVERALL_SCORE",
            field="overall_score",
        )
    return criteria_by_id


def _get_or_create_rater(db: Session, identity: RaterIdentity) -> Rater:
    """Reuse the rater with this external_id, refreshing their display name if it changed."""
    rater = db.scalar(select(Rater).where(Rater.external_id == identity.external_id))
    if rater is None:
        rater = Rater(external_id=identity.external_id, name=identity.name)
        db.add(rater)
        db.flush()
    elif rater.name != identity.name:
        rater.name = identity.name
    return rater


def _find_existing_evaluation(
    db: Session, submission_id: int, rubric_id: int, rater_id: int
) -> Evaluation | None:
    return db.scalar(
        select(Evaluation).where(
            Evaluation.submission_id == submission_id,
            Evaluation.rubric_id == rubric_id,
            Evaluation.rater_id == rater_id,
        )
    )


def _duplicate_evaluation_error(
    external_id: str, submission_id: int, rubric_id: int
) -> ConflictError:
    return ConflictError(
        f"Rater '{external_id}' has already evaluated submission {submission_id} "
        f"with rubric {rubric_id}. Existing evaluations are not overwritten.",
        code="DUPLICATE_EVALUATION",
    )
