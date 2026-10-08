from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.db.models import Criterion, CriterionAnchor, Rubric
from app.schemas.rubrics import RubricCreate

_RUBRIC_LOAD_OPTIONS = (selectinload(Rubric.criteria).selectinload(Criterion.anchors),)


def create_rubric(db: Session, payload: RubricCreate) -> Rubric:
    rubric = Rubric(
        name=payload.name,
        description=payload.description,
        scale_min=payload.scale_min,
        scale_max=payload.scale_max,
        criteria=[
            Criterion(
                name=criterion.name,
                description=criterion.description,
                weight=criterion.weight,
                position=position,
                anchors=[
                    CriterionAnchor(score=a.score, label=a.label, description=a.description)
                    for a in sorted(criterion.anchors, key=lambda a: a.score)
                ],
            )
            for position, criterion in enumerate(payload.criteria)
        ],
    )
    db.add(rubric)
    db.commit()
    return rubric


def get_rubric(db: Session, rubric_id: int, *, field: str | None = None) -> Rubric:
    rubric = db.scalar(select(Rubric).where(Rubric.id == rubric_id).options(*_RUBRIC_LOAD_OPTIONS))
    if rubric is None:
        raise NotFoundError(
            f"Rubric {rubric_id} was not found.", code="RUBRIC_NOT_FOUND", field=field
        )
    return rubric


def list_rubrics(db: Session, *, limit: int, offset: int) -> tuple[list[Rubric], int]:
    total = db.scalar(select(func.count()).select_from(Rubric)) or 0
    rubrics = db.scalars(
        select(Rubric)
        .order_by(Rubric.id)
        .limit(limit)
        .offset(offset)
        .options(*_RUBRIC_LOAD_OPTIONS)
    ).all()
    return list(rubrics), total
