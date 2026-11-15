"""Phase 1 contracts. External adapters remain provisional until integration."""

from typing import Annotated, Literal

from pydantic import Field, StrictFloat, model_validator

from causalbridge.schemas import Record

Finite = Annotated[StrictFloat, Field(allow_inf_nan=False)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Direction = Literal["A_to_B", "B_to_A"]


class Variable(Record):
    name: str = Field(min_length=1)
    unit: str | None = None


class RuntimePair(Record):
    """Loader handoff in original column order; no evaluator fields accepted."""

    case_id: str = Field(pattern=r"^D[0-9]{4,}$")
    variables: tuple[Variable, Variable]
    rows: tuple[tuple[Finite, Finite], ...] = Field(min_length=1)


class SelectionSpec(Record):
    method_limit: int = Field(default=256, ge=1, strict=True)
    display_limit: int = Field(default=64, ge=1, strict=True)
    mapping_seed: int = Field(default=261, ge=0, strict=True)
    sample_seed: int = Field(default=262, ge=0, strict=True)
    display_seed: int = Field(default=263, ge=0, strict=True)

    @model_validator(mode="after")
    def limits(self):
        if self.display_limit > self.method_limit:
            raise ValueError("Display limit cannot exceed method limit")
        return self


class SelectionRecord(Record):
    """Private reproducibility sidecar, excluded from public package."""

    version: Literal["selection-v1"] = "selection-v1"
    case_id: str
    source_digest: Digest
    spec: SelectionSpec
    column_order: tuple[Literal[0, 1], Literal[0, 1]]
    method_indices: tuple[int, ...]
    display_indices: tuple[int, ...]


class SelectedPair(Record):
    case_id: str
    variables: tuple[Variable, Variable]
    method_rows: tuple[tuple[Finite, Finite], ...]
    display_rows: tuple[tuple[Finite, Finite], ...]
    method_sample_digest: Digest
    display_sample_digest: Digest
    selection: SelectionRecord


class Summary(Record):
    n: int = Field(ge=1)
    minimum: Finite
    maximum: Finite
    mean: Finite
    population_std: Finite = Field(ge=0)


class DisplayRow(Record):
    evidence_id: str
    values: tuple[Finite, Finite]


class MethodCard(Record):
    """Compact card, not a regression implementation or full provenance record."""

    evidence_id: Literal["method:anm:v1"] = "method:anm:v1"
    method_version: str = Field(min_length=1)
    sample_digest: Digest
    config_digest: Digest
    n_selected: int = Field(ge=1, strict=True)
    status: Literal["ok", "error"]
    score_ab: Finite | None = None
    score_ba: Finite | None = None
    margin: Finite | None = None
    threshold: Finite | None = Field(default=None, ge=0)
    threshold_version: str | None = None
    predicted_direction: Direction | None = None
    reason_code: str = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "error":
            if any(
                v is not None
                for v in (self.score_ab, self.score_ba, self.margin, self.predicted_direction)
            ):
                raise ValueError("Method error cannot claim scores or a direction")
            return self
        if any(v is None for v in (self.score_ab, self.score_ba, self.margin)):
            raise ValueError("Successful diagnostic requires scores and margin")
        if abs(self.margin - (self.score_ba - self.score_ab)) > 1e-12:
            raise ValueError("Method margin inconsistent with scores")
        if self.threshold is None:
            if (
                self.predicted_direction is not None
                or self.reason_code != "threshold_not_configured"
            ):
                raise ValueError("Unconfigured threshold cannot select direction")
        else:
            if not self.threshold_version:
                raise ValueError("Configured threshold requires a version")
            expected = (
                "A_to_B"
                if self.margin > self.threshold
                else "B_to_A"
                if self.margin < -self.threshold
                else None
            )
            if self.predicted_direction != expected:
                raise ValueError("Method direction inconsistent with margin/threshold")
        return self


class EvidencePackage(Record):
    schema_version: Literal["track-b-v1"] = "track-b-v1"
    task: Literal["causal_direction"] = "causal_direction"
    case_id: str
    package: Literal["E1", "E2", "E3", "E4"]
    question: str
    context: tuple[Variable, Variable] | None = None
    display_rows: tuple[DisplayRow, ...] = ()
    summary: tuple[Summary, Summary] | None = None
    method: MethodCard | None = None
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def availability(self):
        named, numeric = self.package != "E2", self.package != "E1"
        if (self.context is not None) != named:
            raise ValueError("Context does not match package")
        if bool(self.display_rows) != numeric or (self.summary is not None) != numeric:
            raise ValueError("Numeric evidence does not match package")
        if (self.method is not None) != (self.package == "E4"):
            raise ValueError("Method evidence does not match package")
        row_ids = tuple(f"rows:r{i:04d}" for i in range(1, len(self.display_rows) + 1))
        if tuple(r.evidence_id for r in self.display_rows) != row_ids:
            raise ValueError("Row IDs must use local display positions")
        expected = (("context:A", "context:B") if named else ()) + row_ids
        if numeric:
            expected += ("summary:A", "summary:B")
            if any(s.n != len(self.display_rows) for s in self.summary):
                raise ValueError("Summary count does not match display rows")
        if self.method:
            expected += (self.method.evidence_id,)
        if self.evidence_ids != expected:
            raise ValueError("Evidence registry does not match available items")
        return self


class EvidenceEnvelope(Record):
    """Trusted bindings; only payload is serialized into model messages."""

    payload: EvidencePackage
    evidence_digest: Digest
    display_sample_digest: Digest | None
    method_sample_digest: Digest | None


class DirectionProposal(Record):
    response_action: Literal["answer", "abstain"]
    predicted_direction: Direction | None
    evidence_refs: tuple[str, ...]
    method_attribution: Literal["A_to_B", "B_to_A", "abstain", "unavailable"] | None
    claim_scope: Literal["plausible_direction", "causal_proof"]
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def action(self):
        if (self.predicted_direction is not None) != (self.response_action == "answer"):
            raise ValueError("Answer requires direction; abstention requires null")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("Repeated evidence reference")
        return self


class PredictionAttempt(Record):
    """Phase 1 transport example; durable execution is Phase 2."""

    schema_version: Literal["track-b-v1"] = "track-b-v1"
    attempt_id: str = Field(min_length=1)
    evidence_digest: Digest
    condition: Literal["S0", "S1"]
    status: Literal["parsed", "parse_error", "model_error"]
    raw_text: str | None
    proposal: DirectionProposal | None
    failure_code: str | None
    model: str
    model_mode: Literal["scripted_fixture", "live"]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def outcome(self):
        if self.status == "parsed":
            if self.raw_text is None or self.proposal is None or self.failure_code is not None:
                raise ValueError("Parsed attempt requires raw text/proposal and no failure")
        elif self.proposal is not None or not self.failure_code:
            raise ValueError("Failed attempt requires failure code and no proposal")
        if self.status == "parse_error" and self.raw_text is None:
            raise ValueError("Parse failure must preserve raw text")
        return self


class ReleaseRecord(Record):
    """Checker's process outcome, never a certificate of causal correctness."""

    parent_attempt_id: str
    parent_attempt_digest: Digest
    checker_version: str
    process_status: Literal["passed", "rejected", "error", "not_checked"]
    response_action: Literal["answer", "abstain"]
    released_direction: Direction | None
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def release(self):
        if (self.released_direction is not None) != (self.response_action == "answer"):
            raise ValueError("Released direction and action disagree")
        if self.released_direction and self.process_status != "passed":
            raise ValueError("Only a passed process check can release a direction")
        return self
