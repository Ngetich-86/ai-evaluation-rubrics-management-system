import json
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator

from app.schemas.common import InputModel, LongText, Name, ReadModel
from app.schemas.evaluations import EvaluationRead

MAX_METADATA_BYTES = 20_000


class SubmissionCreate(InputModel):
    prompt: LongText = Field(examples=["Explain why idempotency matters in payment APIs."])
    output: LongText = Field(examples=["Idempotency prevents repeated requests from..."])
    model_name: Name = Field(examples=["example-model"])
    model_version: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = Field(default=None, examples=["v1"])
    model_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary JSON object, e.g. sampling parameters or run identifiers.",
        examples=[{"temperature": 0.2, "provider": "example"}],
    )
    reference_answer: LongText | None = None

    @field_validator("model_metadata")
    @classmethod
    def limit_metadata_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and len(json.dumps(value)) > MAX_METADATA_BYTES:
            raise ValueError(f"model_metadata must serialise to <= {MAX_METADATA_BYTES} bytes.")
        return value


class SubmissionRead(ReadModel):
    id: int
    prompt: str
    output: str
    model_name: str
    model_version: str | None
    model_metadata: dict[str, Any] | None
    reference_answer: str | None
    created_at: datetime
    evaluations: list[EvaluationRead]


class SubmissionSummary(ReadModel):
    """Compact submission listing entry; fetch the submission for full text and evaluations."""

    id: int
    model_name: str
    model_version: str | None
    prompt_preview: str = Field(description="First characters of the prompt.")
    evaluation_count: int
    created_at: datetime


class SubmissionList(ReadModel):
    items: list[SubmissionSummary]
    total: int
    limit: int
    offset: int
