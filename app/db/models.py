"""ORM models.

    Rubric 1──N Criterion 1──N CriterionAnchor
    Submission 1──N Evaluation N──1 Rubric
                    Evaluation N──1 Rater
                    Evaluation 1──N CriterionScore N──1 Criterion

Cascades: deleting a rubric removes its criteria and anchors; deleting a submission
removes its evaluations and their criterion scores. A rubric, criterion or rater that is
referenced by an evaluation cannot be deleted (RESTRICT), so scores are never orphaned.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow

JsonDocument = JSON().with_variant(JSONB(), "postgresql")


class Rubric(Base):
    __tablename__ = "rubrics"
    __table_args__ = (CheckConstraint("scale_min < scale_max", name="ck_rubrics_scale_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    scale_min: Mapped[int] = mapped_column(Integer)
    scale_max: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    criteria: Mapped[list["Criterion"]] = relationship(
        back_populates="rubric",
        cascade="all, delete-orphan",
        order_by="Criterion.position",
    )


class Criterion(Base):
    __tablename__ = "criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "name", name="uq_criteria_rubric_name"),
        CheckConstraint("weight > 0", name="ck_criteria_weight_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    position: Mapped[int] = mapped_column(Integer)

    rubric: Mapped[Rubric] = relationship(back_populates="criteria")
    anchors: Mapped[list["CriterionAnchor"]] = relationship(
        back_populates="criterion",
        cascade="all, delete-orphan",
        order_by="CriterionAnchor.score",
    )


class CriterionAnchor(Base):
    __tablename__ = "criterion_anchors"
    __table_args__ = (UniqueConstraint("criterion_id", "score", name="uq_anchors_criterion_score"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("criteria.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    criterion: Mapped[Criterion] = relationship(back_populates="anchors")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(200), index=True)
    model_version: Mapped[str | None] = mapped_column(String(100))
    model_metadata: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="Evaluation.id",
    )


class Rater(Base):
    __tablename__ = "raters"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "rubric_id", "rater_id", name="uq_evaluations_submission_rubric_rater"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    rubric_id: Mapped[int] = mapped_column(
        ForeignKey("rubrics.id", ondelete="RESTRICT"), index=True
    )
    rater_id: Mapped[int] = mapped_column(ForeignKey("raters.id", ondelete="RESTRICT"), index=True)
    overall_score: Mapped[int] = mapped_column(Integer)
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    submission: Mapped[Submission] = relationship(back_populates="evaluations")
    rubric: Mapped[Rubric] = relationship()
    rater: Mapped[Rater] = relationship()
    criterion_scores: Mapped[list["CriterionScore"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


class CriterionScore(Base):
    __tablename__ = "criterion_scores"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id", "criterion_id", name="uq_criterion_scores_eval_criterion"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("criteria.id", ondelete="RESTRICT"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped[Evaluation] = relationship(back_populates="criterion_scores")
    criterion: Mapped[Criterion] = relationship()
