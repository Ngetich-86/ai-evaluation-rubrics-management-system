from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.errors import error_responses
from app.db.session import DbSession
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.schemas.rubrics import RubricCreate, RubricList, RubricRead
from app.services import rubric_service

router = APIRouter(prefix="/rubrics", tags=["Rubrics"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a rubric",
    description=(
        "Create a rubric with a shared integer scoring scale and one or more criteria. "
        "Each criterion needs a positive weight (default 1.0) and exactly one descriptive anchor "
        "for every integer score from `scale_min` to `scale_max`. Criterion names must be unique."
    ),
)
def create_rubric(payload: RubricCreate, db: DbSession) -> RubricRead:
    return RubricRead.model_validate(rubric_service.create_rubric(db, payload))


@router.get(
    "", summary="List rubrics", description="Rubrics ordered by id, with limit/offset paging."
)
def list_rubrics(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RubricList:
    rubrics, total = rubric_service.list_rubrics(db, limit=limit, offset=offset)
    return RubricList(
        items=[RubricRead.model_validate(r) for r in rubrics],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{rubric_id}",
    summary="Get a rubric",
    description="A rubric with its criteria, weights and anchors.",
    responses=error_responses(status.HTTP_404_NOT_FOUND),
)
def get_rubric(rubric_id: int, db: DbSession) -> RubricRead:
    return RubricRead.model_validate(rubric_service.get_rubric(db, rubric_id))
