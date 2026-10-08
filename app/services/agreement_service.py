"""Inter-rater agreement for a single submission.

The rated units are the rubric's criteria: each rater contributes one integer score per
criterion on the rubric's shared scale, and Cohen's kappa is computed for every pair of
raters over those score vectors.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from statistics import fmean

from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError
from app.db.models import Evaluation, Rater
from app.schemas.analysis import AgreementRead, PairwiseAgreement, RaterRef
from app.services import evaluation_service, rubric_service

AGREEMENT_PRECISION = 4
MIN_EVALUATIONS_FOR_AGREEMENT = 2

AGREEMENT_NOTE = (
    "Agreement is calculated across rubric criteria for this single submission, treating each "
    "criterion as one rated unit. With few criteria the estimate is unstable and should be "
    "interpreted cautiously. Unweighted kappa treats every disagreement equally, regardless of "
    "how far apart the scores are."
)
UNDEFINED_KAPPA_NOTE = (
    "Kappa is undefined because expected agreement is 1: both raters gave every criterion the "
    "same single score, so chance-corrected agreement cannot be estimated."
)


@dataclass(frozen=True)
class KappaResult:
    observed_agreement: float
    expected_agreement: float
    kappa: float | None
    """None when expected agreement equals 1, where (Po - Pe) / (1 - Pe) is 0/0."""


def cohens_kappa(ratings_a: Sequence[int], ratings_b: Sequence[int]) -> KappaResult:
    """Unweighted Cohen's kappa for two raters scoring the same units.

    Po is the share of units with identical scores. Pe is the chance agreement implied by each
    rater's own marginal score frequencies: sum over scores k of P_a(k) * P_b(k).
    Exact fractions are used so the degenerate case Pe == 1 is detected without float error.
    """
    if len(ratings_a) != len(ratings_b):
        raise ValueError("Both raters must score the same number of units.")
    if not ratings_a:
        raise ValueError("At least one rated unit is required.")

    n = len(ratings_a)
    observed = Fraction(sum(a == b for a, b in zip(ratings_a, ratings_b, strict=True)), n)
    counts_a, counts_b = Counter(ratings_a), Counter(ratings_b)
    expected = Fraction(sum(counts_a[k] * counts_b[k] for k in counts_a), n * n)

    kappa = None if expected == 1 else float((observed - expected) / (1 - expected))
    return KappaResult(float(observed), float(expected), kappa)


def compute_submission_agreement(
    db: Session, submission_id: int, rubric_id: int | None = None
) -> AgreementRead:
    evaluations = evaluation_service.list_evaluations(db, submission_id, rubric_id=rubric_id)
    rubric_id = _resolve_rubric_id(evaluations, rubric_id)
    evaluations = [e for e in evaluations if e.rubric_id == rubric_id]

    if len(evaluations) < MIN_EVALUATIONS_FOR_AGREEMENT:
        raise ConflictError(
            "At least two evaluations using the same rubric are required to calculate "
            f"agreement; found {len(evaluations)}.",
            code="INSUFFICIENT_EVALUATIONS",
        )

    rubric = rubric_service.get_rubric(db, rubric_id)
    criterion_ids = [criterion.id for criterion in rubric.criteria]
    evaluations.sort(key=lambda e: e.rater.external_id)
    vectors = {e.id: _score_vector(e, criterion_ids) for e in evaluations}

    pairwise: list[PairwiseAgreement] = []
    for eval_a, eval_b in combinations(evaluations, 2):
        result = cohens_kappa(vectors[eval_a.id], vectors[eval_b.id])
        pairwise.append(
            PairwiseAgreement(
                rater_a=_rater_ref(eval_a.rater),
                rater_b=_rater_ref(eval_b.rater),
                scores_a=vectors[eval_a.id],
                scores_b=vectors[eval_b.id],
                compared_criteria=len(criterion_ids),
                observed_agreement=_round(result.observed_agreement),
                expected_agreement=_round(result.expected_agreement),
                kappa=None if result.kappa is None else _round(result.kappa),
                kappa_note=UNDEFINED_KAPPA_NOTE if result.kappa is None else None,
            )
        )

    defined_kappas = [p.kappa for p in pairwise if p.kappa is not None]
    return AgreementRead(
        submission_id=submission_id,
        rubric_id=rubric_id,
        rater_count=len(evaluations),
        criterion_count=len(criterion_ids),
        criterion_ids=criterion_ids,
        pairwise=pairwise,
        mean_pairwise_kappa=_round(fmean(defined_kappas)) if defined_kappas else None,
        mean_pairwise_exact_agreement=_round(fmean(p.observed_agreement for p in pairwise)),
        note=AGREEMENT_NOTE,
    )


def _resolve_rubric_id(evaluations: list[Evaluation], rubric_id: int | None) -> int:
    if rubric_id is not None:
        return rubric_id
    rubric_ids = sorted({e.rubric_id for e in evaluations})
    if len(rubric_ids) > 1:
        raise BusinessRuleError(
            f"This submission has evaluations for multiple rubrics {rubric_ids}; "
            "specify ?rubric_id=<id>.",
            code="RUBRIC_ID_REQUIRED",
            field="rubric_id",
        )
    if not rubric_ids:
        raise ConflictError(
            "At least two evaluations using the same rubric are required to calculate "
            "agreement; found 0.",
            code="INSUFFICIENT_EVALUATIONS",
        )
    return rubric_ids[0]


def _score_vector(evaluation: Evaluation, criterion_ids: list[int]) -> list[int]:
    # Complete scoring is enforced on write, so every criterion has exactly one score.
    by_criterion = {cs.criterion_id: cs.score for cs in evaluation.criterion_scores}
    return [by_criterion[cid] for cid in criterion_ids]


def _rater_ref(rater: Rater) -> RaterRef:
    return RaterRef(id=rater.id, external_id=rater.external_id, name=rater.name)


def _round(value: float) -> float:
    return round(value, AGREEMENT_PRECISION)
