from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import (
    MAX_DESCRIPTION_LENGTH,
    InputModel,
    LongText,
    Name,
    ReadModel,
    Score,
)
from app.schemas.rubrics import MAX_CRITERIA, RubricSummary

ExternalId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:@-]+$"
    ),
]
Comment = Annotated[str, StringConstraints(max_length=MAX_DESCRIPTION_LENGTH)]


class RaterIdentity(InputModel):
    external_id: ExternalId = Field(
        description="Stable evaluator identifier; reused across evaluations.",
        examples=["rater-001"],
    )
    name: Name = Field(examples=["Evaluator One"])


class CriterionScoreCreate(InputModel):
    criterion_id: int = Field(gt=0)
    score: Score
    comment: Comment | None = None


class EvaluationCreate(InputModel):
    rubric_id: int = Field(gt=0)
    rater: RaterIdentity
    criterion_scores: list[CriterionScoreCreate] = Field(min_length=1, max_length=MAX_CRITERIA)
    overall_score: Score = Field(description="Evaluator-provided holistic score.")
    comments: LongText | None = None


class RaterRead(ReadModel):
    id: int
    external_id: str
    name: str
    created_at: datetime


class CriterionScoreRead(ReadModel):
    id: int
    criterion_id: int
    criterion_name: str
    weight: float
    score: int
    comment: str | None


class DerivedScores(ReadModel):
    """System-derived statistics. They never replace the evaluator's overall_score."""

    mean_criterion_score: float
    weighted_mean_criterion_score: float = Field(
        description="sum(score * weight) / sum(weight) across the rubric's criteria."
    )


class EvaluationRead(ReadModel):
    id: int
    submission_id: int
    rubric: RubricSummary
    rater: RaterRead
    overall_score: int = Field(description="Evaluator-provided holistic score.")
    comments: str | None
    criterion_scores: list[CriterionScoreRead]
    derived: DerivedScores = Field(description="System-derived; not provided by the evaluator.")
    created_at: datetime
