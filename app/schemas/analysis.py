from pydantic import BaseModel, Field


class RaterRef(BaseModel):
    id: int
    external_id: str
    name: str


class PairwiseAgreement(BaseModel):
    rater_a: RaterRef
    rater_b: RaterRef
    scores_a: list[int] = Field(description="Rater A's scores, in rubric criterion order.")
    scores_b: list[int] = Field(description="Rater B's scores, in rubric criterion order.")
    compared_criteria: int
    observed_agreement: float = Field(description="Po: share of criteria with identical scores.")
    expected_agreement: float = Field(
        description="Pe: chance agreement from each rater's marginal score frequencies."
    )
    kappa: float | None = Field(
        description="Cohen's kappa = (Po - Pe) / (1 - Pe). Null when undefined (Pe = 1)."
    )
    kappa_note: str | None = None


class AgreementRead(BaseModel):
    submission_id: int
    rubric_id: int
    method: str = "cohens_kappa_pairwise"
    rater_count: int
    criterion_count: int
    criterion_ids: list[int] = Field(description="Criterion order used for the score vectors.")
    pairwise: list[PairwiseAgreement]
    mean_pairwise_kappa: float | None = Field(
        description="Mean of the defined pairwise kappas. Null if no pair has a defined kappa."
    )
    mean_pairwise_exact_agreement: float
    note: str
