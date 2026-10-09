from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Input-size limits. Generous for real LLM outputs, but bounded.
MAX_NAME_LENGTH = 200
MAX_LABEL_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 4_000
MAX_LONG_TEXT_LENGTH = 100_000

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH)
]
Description = Annotated[str, StringConstraints(max_length=MAX_DESCRIPTION_LENGTH)]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LONG_TEXT_LENGTH)
]
# Scores are strict integers: "4" or true are rejected rather than coerced.
Score = Annotated[int, Field(strict=True)]


class InputModel(BaseModel):
    """Base for request bodies: unknown fields are rejected to catch client typos."""

    model_config = ConfigDict(extra="forbid")


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str = Field(examples=["INVALID_CRITERION_SCORE"])
    message: str = Field(examples=["Score 6 is outside rubric scale 1-5."])
    field: str | None = Field(default=None, examples=["criterion_scores[1].score"])


class ErrorResponse(BaseModel):
    detail: ErrorDetail
