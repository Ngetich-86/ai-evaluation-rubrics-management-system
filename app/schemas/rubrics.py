from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import (
    MAX_LABEL_LENGTH,
    Description,
    InputModel,
    Name,
    ReadModel,
    Score,
)

MIN_SCALE_VALUE = -100
MAX_SCALE_VALUE = 100
MAX_SCALE_POINTS = 11  # e.g. 0-10
MAX_CRITERIA = 50
MAX_WEIGHT = 1_000.0

Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LABEL_LENGTH)
]


class AnchorCreate(InputModel):
    score: Score
    label: Label = Field(examples=["Excellent"])
    description: Description | None = None


class CriterionCreate(InputModel):
    name: Name = Field(examples=["Correctness"])
    description: Description | None = None
    weight: float = Field(default=1.0, gt=0, le=MAX_WEIGHT)
    anchors: list[AnchorCreate] = Field(min_length=1, max_length=MAX_SCALE_POINTS)


class RubricCreate(InputModel):
    name: Name = Field(examples=["General Response Quality"])
    description: Description | None = None
    scale_min: Score = Field(ge=MIN_SCALE_VALUE, le=MAX_SCALE_VALUE, examples=[1])
    scale_max: Score = Field(ge=MIN_SCALE_VALUE, le=MAX_SCALE_VALUE, examples=[5])
    criteria: list[CriterionCreate] = Field(min_length=1, max_length=MAX_CRITERIA)

    @model_validator(mode="after")
    def validate_scale_and_anchors(self) -> Self:
        if self.scale_min >= self.scale_max:
            raise ValueError(
                f"scale_min ({self.scale_min}) must be less than scale_max ({self.scale_max})."
            )
        scale_points = self.scale_max - self.scale_min + 1
        if scale_points > MAX_SCALE_POINTS:
            raise ValueError(f"The scale may have at most {MAX_SCALE_POINTS} points.")

        seen_names: set[str] = set()
        for index, criterion in enumerate(self.criteria):
            key = criterion.name.casefold()
            if key in seen_names:
                raise ValueError(f"criteria[{index}]: duplicate criterion name '{criterion.name}'.")
            seen_names.add(key)
            self._validate_anchors(index, criterion)
        return self

    def _validate_anchors(self, index: int, criterion: CriterionCreate) -> None:
        where = f"criteria[{index}] ('{criterion.name}')"
        scores = [anchor.score for anchor in criterion.anchors]

        out_of_range = sorted(s for s in scores if not self.scale_min <= s <= self.scale_max)
        if out_of_range:
            raise ValueError(
                f"{where}: anchor scores {out_of_range} are outside the rubric scale "
                f"{self.scale_min}-{self.scale_max}."
            )
        duplicates = sorted({s for s in scores if scores.count(s) > 1})
        if duplicates:
            raise ValueError(f"{where}: duplicate anchor scores {duplicates}.")
        missing = sorted(set(range(self.scale_min, self.scale_max + 1)) - set(scores))
        if missing:
            raise ValueError(
                f"{where}: an anchor is required for every score on the scale; missing {missing}."
            )


class AnchorRead(ReadModel):
    id: int
    score: int
    label: str
    description: str | None


class CriterionRead(ReadModel):
    id: int
    name: str
    description: str | None
    weight: float
    position: int
    anchors: list[AnchorRead]


class RubricRead(ReadModel):
    id: int
    name: str
    description: str | None
    scale_min: int
    scale_max: int
    created_at: datetime
    updated_at: datetime
    criteria: list[CriterionRead]


class RubricSummary(ReadModel):
    """Compact rubric reference embedded in evaluation responses."""

    id: int
    name: str
    scale_min: int
    scale_max: int


class RubricList(ReadModel):
    items: list[RubricRead]
    total: int
    limit: int
    offset: int
