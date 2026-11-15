"""Provisional Track B v0.1 contracts, independent of Track A effect schemas."""

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from causalbridge.schemas import Number, Record

Direction = Literal["A_to_B", "B_to_A"]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(strict=True, ge=0)]
Seed = Annotated[int, Field(strict=True)]
Nonnegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


def canonical_digest(payload: object) -> str:
    """Hash UTF-8 canonical JSON v1: sorted keys, compact, ASCII, no NaN.

    Sequence order is significant; numeric 1 and 1.0 remain distinct. Callers
    hash validated model JSON to normalize numbers before computing identities.
    """
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class ANMProvenance(Record):
    """Runtime-safe identifiers, never source dataset/column names or labels.

    reproducibility_ref is a content digest of an immutable external record
    containing per-variable transforms, training-only means/scales, residual
    scaling, evaluation transforms, regression/kernel/hyperparameters, HSIC
    estimator/bandwidth/score convention, threshold version and dependencies.
    The adapter must verify that record; Phase 1 does not resolve references.
    """

    sample_digest: Digest
    ab_mapping_id: Identifier
    selected_row_count: Count
    training_row_count: Count
    evaluation_row_count: Count
    sampling_seed: Seed
    split_seed: Seed
    config_digest: Digest
    method_version: Identifier
    configuration_version: Identifier
    reproducibility_ref: Digest
    validation_findings: tuple[str, ...]
    input_quality_warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_counts(self):
        if self.training_row_count + self.evaluation_row_count != self.selected_row_count:
            raise ValueError("Training and evaluation counts must partition the selected sample")
        return self


class ANMResult(Record):
    """Cached diagnostic, not a probability or proof; no ANM execution here."""

    status: Literal["ok", "error"]
    score_ab: Number | None = None
    score_ba: Number | None = None
    margin: Number | None = None
    threshold: Nonnegative | None = None
    decision: Direction | Literal["abstain"] | None = None
    predicted_direction: Direction | None = None
    reason_code: Identifier | None = None
    error_category: (
        Literal["input_validation", "configuration", "regression", "dependence"] | None
    ) = None
    provenance: ANMProvenance
    limitations: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "error":
            if (
                any(
                    v is not None
                    for v in (
                        self.score_ab,
                        self.score_ba,
                        self.margin,
                        self.decision,
                        self.predicted_direction,
                    )
                )
                or not self.reason_code
                or not self.error_category
            ):
                raise ValueError("Errors require a category/reason and no scores or direction")
            return self
        if self.error_category is not None:
            raise ValueError("Successful diagnostics cannot have an error category")
        if any(v is None for v in (self.score_ab, self.score_ba, self.margin)):
            raise ValueError("Successful diagnostics require both scores and margin")
        # Unbiased HSIC estimators can be negative; do not invent a positive range.
        if not math.isclose(
            self.margin, self.score_ba - self.score_ab, rel_tol=1e-9, abs_tol=1e-12
        ):
            raise ValueError("Margin must equal score_ba - score_ab")
        if min(self.provenance.training_row_count, self.provenance.evaluation_row_count) < 1:
            raise ValueError("Successful diagnostics require training and evaluation rows")
        if self.threshold is None:
            if (
                self.decision is not None
                or self.predicted_direction is not None
                or self.reason_code != "threshold_not_configured"
            ):
                raise ValueError("Unconfigured threshold must not produce a decision")
        else:
            # A tolerated reporting discrepancy must not create a direction that
            # the saved scores do not support, especially when tau is zero.
            score_difference = self.score_ba - self.score_ab
            expected = (
                "A_to_B"
                if score_difference > self.threshold
                else "B_to_A"
                if score_difference < -self.threshold
                else "abstain"
            )
            direction = None if expected == "abstain" else expected
            if self.decision != expected or self.predicted_direction != direction:
                raise ValueError("Decision must follow the symmetric threshold rule")
            if self.reason_code != ("ambiguous_margin" if expected == "abstain" else None):
                raise ValueError("Configured decision reason is inconsistent")
        return self


class NumericSummary(Record):
    """Optional supplied statistics of displayed rows only, ordered A then B."""

    source: Literal["display_rows"] = "display_rows"
    n_display: Count
    mean: tuple[Number, Number] | None = None
    std: tuple[Nonnegative, Nonnegative] | None = None
    minimum: tuple[Number, Number] | None = None
    maximum: tuple[Number, Number] | None = None
    correlation: Annotated[float, Field(strict=True, ge=-1, le=1)] | None = None


class DirectionEvidence(Record):
    schema_version: Literal["0.1"] = "0.1"
    task: Literal["causal_direction"] = "causal_direction"
    case_id: Identifier
    package: Literal["E1", "E2", "E3", "E4"]
    ab_mapping_id: Identifier
    mapping_seed: Seed
    variable_labels: tuple[Identifier, Identifier] | None = None
    units: tuple[str | None, str | None] | None = None
    display_rows: tuple[tuple[Number, Number], ...] | None = None
    display_sampling_seed: Seed | None = None
    summary: NumericSummary | None = None
    method_result: ANMResult | None = None

    @model_validator(mode="after")
    def validate_package(self):
        if self.package == "E1":
            if any(
                v is not None
                for v in (
                    self.display_rows,
                    self.summary,
                    self.display_sampling_seed,
                    self.method_result,
                )
            ):
                raise ValueError("E1 permits names and units only")
        elif not self.display_rows or self.summary is None or self.display_sampling_seed is None:
            raise ValueError("E2–E4 require displayed rows, summary and sampling seed")
        if self.package == "E2":
            if self.variable_labels is not None or self.units is not None:
                raise ValueError("E2 must use anonymous A/B without names or units")
        elif self.variable_labels is None:
            raise ValueError("Named packages require sanitized labels")
        if self.summary is not None and self.summary.n_display != len(self.display_rows or ()):
            raise ValueError("Summary n_display must match displayed row count")
        if (self.method_result is not None) != (self.package == "E4"):
            raise ValueError("Exactly E4 must contain a cached method result")
        if self.method_result and self.method_result.provenance.ab_mapping_id != self.ab_mapping_id:
            raise ValueError("Method A/B mapping does not match evidence")
        return self

    @property
    def display_sample_digest(self) -> str | None:
        if self.display_rows is None:
            return None
        data = self.model_dump(mode="json")
        return canonical_digest(
            {
                k: data[k]
                for k in ("ab_mapping_id", "mapping_seed", "display_rows", "display_sampling_seed")
            }
        )

    @property
    def package_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class MethodDirectionClaim(Record):
    type: Literal["method_direction"]
    evidence_ref: Literal["method_result"]
    direction: Direction | None


class DisplayRowClaim(Record):
    type: Literal["display_row"]
    evidence_ref: Literal["display_rows"]
    row_index: Count
    values: tuple[Number, Number]


class SummaryClaim(Record):
    type: Literal["summary"]
    evidence_ref: Literal["summary"]
    statistic: Literal["mean", "std", "minimum", "maximum", "correlation", "n_display"]
    value: Number | tuple[Number, Number]


Claim = Annotated[
    MethodDirectionClaim | DisplayRowClaim | SummaryClaim, Field(discriminator="type")
]


class DirectionPrediction(Record):
    case_id: Identifier
    package_digest: Digest
    predicted_direction: Direction | None
    abstained: StrictBool
    reason_code: Identifier | None = None
    claims: tuple[Claim, ...] = ()

    @model_validator(mode="after")
    def validate_abstention(self):
        if self.abstained != (self.predicted_direction is None):
            raise ValueError("Null direction must be consistent with abstention")
        if self.abstained and self.reason_code is None:
            raise ValueError("Abstention requires a reason")
        return self

    @property
    def proposal_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class PromptCondition(Record):
    """Runner-owned prompt selection. No built-in S0/S1 templates."""

    condition_id: Identifier
    version: Identifier
    instructions: Identifier
