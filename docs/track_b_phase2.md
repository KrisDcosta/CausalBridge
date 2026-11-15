# Track B Phase 2: deterministic evidence and claim verification

Implemented against the November 8 Detailed Implementation Roadmap, Section 6
V2 and Section 7, the team interface agreement, and the Phase 1 handoff.
The verifier checks declared evidence use, not causal truth. Reference-direction
accuracy remains an evaluator task. All examples and tests here are scripted;
none estimates naturally occurring model errors or predictive performance.

## Scope and compatibility

Phase 1 DirectionEvidence, ANMResult, claims, DirectionPrediction, predictor and
transport are unchanged. Track A is untouched. PredictionCheck keeps its fields
and release invariant; its default checker_version is now `direction-checker-0.2`.
The Phase 1 placeholder implementation is replaced. Historical Phase 1 JSONL
checks remain archived results, not expected outputs of the Phase 2 checker.

The two-argument checker call remains valid. A keyword-only `context` supplies
trusted original records; omitting it cannot release an answer. Two Phase 1 tests
that asserted placeholder reason codes now assert the implemented behavior.
No ANM, loader, scoring, caching, runner, training, agent or LLM verifier is added.

## Exact callable interface for Kris

```python
from causalbridge.discovery.schemas import DirectionEvidence, DirectionPrediction
from causalbridge.verifier.bindings import VerificationContext
from causalbridge.verifier.checks import PredictionCheck, check_prediction


def check_prediction(
    evidence: DirectionEvidence,
    saved_prediction: DirectionPrediction,
    *,
    context: VerificationContext | None = None,
) -> PredictionCheck: ...
```

Runner integration sequence (not implemented here):

1. Before ANM executes, persist ANMRequestBinding from the actual request inputs.
   Do not create this binding by copying the returned result's provenance.
2. Before S1 prediction, persist the exact model-visible DirectionEvidence,
   package/display/mapping identities, and digest of the cached ANMResult if E4.
3. After successful S1 parsing/binding, persist the original DirectionPrediction
   and its proposal_digest with the evidence receipt. Do not use an execution
   whose failure_stage is non-null. Cache the raw Generation as in Phase 1.
4. Load that independent receipt as VerificationContext. Pass the saved evidence
   and saved S1 to check_prediction. Never regenerate expected receipt values
   from candidate records at checking time.
5. Persist PredictionCheck. If release=true, use exactly the saved S1 direction;
   otherwise release no directional answer. The checker never returns a replacement.

Example consumption:

```python
# Loaded from trusted runtime storage, not evaluator rows or the candidate result.
context = VerificationContext.model_validate(saved_receipt_json)
result = check_prediction(saved_evidence, saved_s1, context=context)
released_direction = saved_s1.predicted_direction if result.release else None
```

No resolver is invoked, no filesystem/network lookup occurs inside the checker,
and there is no model/method dependency parameter. Verification is deterministic:
schema validation, hashing, fixed comparisons and one linear pass over claims.
Work scales with the supplied records; no search, resampling or numerical fitting.
Malformed non-JSON values/nonfinite bypassed models or malformed context schemas
raise at the API boundary. JSON-representable malformed evidence/predictions
return a failing PredictionCheck; malformed claim entries get explicit findings.

## Trusted records and expected Anish fields

`ANMRequestBinding` is a new frozen, extra-forbid, verifier-only Record:

| Field | Required source |
| --- | --- |
| case_id | Opaque runtime case identifier |
| ab_mapping_id | Original opaque A/B orientation identity, no raw dataset columns |
| sample_digest | Hash of actual method-input sample and its A/B orientation |
| config_digest | Hash of original frozen method configuration |
| selected_row_count | Actual method sample size |
| training_row_count, evaluation_row_count | Original split sizes; must partition selected rows |
| sampling_seed, split_seed | Original sampling and train/evaluation split seeds |
| threshold | Frozen nonnegative tau, or null when unconfigured |
| method_version, configuration_version | Original method and configuration identities |

Anish's result still uses the unchanged Phase 1 ANMResult/ANMProvenance: scores,
margin, threshold, decision/direction, status/reason/category, limitations,
sample/mapping/config identities, counts/seeds/versions, findings/warnings and
immutable reproducibility_ref. Every corresponding request field is compared
against the result. A method error may retain its configured threshold.

`VerificationContext` is a new frozen, extra-forbid Record loaded from Kris's
trusted original successful-S1 cache:

| Field | Binding checked |
| --- | --- |
| case_id | Original runtime case |
| package_digest | Exact originally shown evidence package |
| proposal_digest | Exact cached parsed S1, including direction and every claim |
| ab_mapping_id, mapping_seed | Original A/B orientation assignment |
| display_sample_digest | Original displayed sample, null for E1 |
| method_result_digest | Original cached ANMResult hash, required for releasing E4 |
| method_request | Independently saved ANMRequestBinding, required for releasing E4 |

Both optional method fields default to null to represent missing trust records.
For non-E4, supplying method context is a contradiction: that evidence contains
no method result. Do not pass these verifier-only records into model prompts.
No evaluator fields are accepted in either record.

The method_result_digest is `canonical_digest(anm_result.model_dump(mode="json"))`.
All other identity conventions reuse Phase 1. In particular, the displayed and
method-input samples have **separate digests and sizes**. Their hashes are never
compared to one another. E2/E3/E4 matching remains Kris's packaging responsibility.

This chooses the **original request** route rather than a record resolver. The
checker does not load the linked reproducibility record. Its reference, warnings,
limitations and all other saved ANM fields are protected against substitution by
the original result/package hashes. Record availability, actual preprocessing,
kernel/HSIC correctness and dependency reproduction remain Anish's responsibility.

## Evidence and ANM checks

Every call snapshots and revalidates records. The snapshot includes undeclared
fields inserted through Pydantic model_copy, including nested claims/results;
ordinary model_dump would silently discard some of those invalid fields.
No original object is modified.

Check the S1 case/package IDs against evidence, then compare evidence/proposal,
mapping/seed and display identities against the independent saved context.
E4 additionally requires its original result digest and independently saved
method request, and compares every request field above. No claimed direction is
trusted merely because a result contains the same copied digest.

ANM schema revalidation rechecks the agreed semantics: finite scores,
margin=score_ba-score_ab within relative tolerance 1e-9 and absolute tolerance
1e-12; decision derived from the recomputed saved-score difference using strict
>tau / <-tau comparisons; otherwise abstain. Equality at either boundary abstains.
The reporting tolerance cannot turn tied scores into a direction. Preserve full
float precision near the threshold, following Phase 1. Negative HSIC scores are
not forbidden because estimator conventions remain Anish's responsibility.

Unconfigured threshold: scores may exist, but decision/direction must be null
with threshold_not_configured. Error: stable reason/category, no scores/margin/
decision/direction. Ambiguous results are successful diagnostics with abstention,
not execution errors. No score or margin is interpreted as causal probability.

## Typed claims and release policy

| Claim | Verification |
| --- | --- |
| method_direction | Configured successful ANM's predicted_direction, including null for a genuine ambiguous decision |
| display_row | Zero-based row exists and both A/B numeric values equal the original displayed row |
| summary | Requested saved statistic exists and the supplied scalar/A-B tuple equals it |

Numeric citations use exact saved-value equality, not a new tolerance that would
permit inaccurate quotation. For n_display, integral numeric 2.0 equals count 2;
scalar/vector shape mismatches fail. Summary validation compares supplied values,
not newly computed statistics: e.g., std convention is not inferred or recomputed.

There is no confidence/probability/score-interpretation claim type in Phase 1.
It remains deliberately absent. Extra probability/confidence fields, unsupported
claim types/references, negative/bool indices and unknown statistics fail schema
validation; if such entries bypass predictor parsing via model_copy, the checker
returns invalid_prediction with claim_schema_invalid findings. It does not parse
reason_code strings as prose or attempt unrestricted natural-language checking.

Method-direction null means a configured ANM abstention. It cannot be used as a
direction claim for an execution error or an unconfigured threshold. There is
no typed error-attribution claim; omit method_direction in those cases.
An honest LLM disagreement with ANM **passes**. The check never compares the
LLM arrow to ANM's preference as a release rule. Similarly a failed/ambiguous/
unconfigured ANM does not force the LLM to abstain if it makes no false method claim.

Release policy, in precedence order:

1. Any schema error, binding contradiction or unsupported/false claim: fail,
   release=false. Known contradictions take precedence over missing trust data.
2. No contradiction, but missing verification context/original E4 request/result
   binding: abstain, release=false. This is checker uncertainty, not scientific
   evidence insufficiency.
3. All bindings and declared claims consistent: pass. If S1 already abstained,
   release=false with prediction_abstained; otherwise release=true with
   evidence_consistent. A pass is only process consistency, never causal truth.

No minimum number of claims is imposed. Empty claims can pass after all relevant
bindings validate; this is a limited declared-evidence check, not a requirement
for an empirical causal argument. If a model abstains but makes false claims,
it fails rather than being exempted. Per-claim findings are independent of other
claims' order. A locally true citation cannot pass against an unbound original
cache; row/summary findings remain checkable when only method request data is missing.

## Complete reason-code vocabulary

Codes are stable machine-readable identifiers. Top-level codes are deduplicated
in deterministic encounter order. Every claim receives one indexed finding
unless evidence/proposal schema validation prevents evaluation. Findings do not
contain reference labels. A fail dominates all abstain findings in the final status.

| Code | Meaning / use |
| --- | --- |
| evidence_consistent | All applicable checks pass and S1 answered; release=true |
| prediction_abstained | All checks pass, S1 abstained; release=false |
| invalid_evidence | Evidence/package/ANM schema revalidation failed; fail |
| invalid_prediction | Proposal/claim schema revalidation failed; fail |
| claim_schema_invalid | Per-claim malformed type, reference, field, index or value; fail finding |
| case_id_mismatch | S1 or receipt case differs from evidence; fail |
| package_digest_mismatch | S1 or receipt package differs from exact evidence; fail |
| proposal_digest_mismatch | Candidate proposal differs from cached S1 receipt; fail |
| ab_mapping_mismatch | Evidence mapping/seed differs from original receipt, or method request mapping differs; fail |
| display_sample_mismatch | Display sample differs from receipt; fail |
| verification_context_missing | No independently saved runtime receipt; abstain absent contradictions |
| method_result_binding_missing | E4 receipt lacks original cached result hash; abstain absent contradictions |
| method_result_mismatch | Cached ANM result differs from original hash; fail |
| method_request_missing | E4 lacks independent original request; abstain absent contradictions |
| method_case_mismatch | Original method request belongs to another case; fail |
| method_sample_mismatch | Result uses a different sample than the original method request; fail |
| method_config_mismatch | Config digest, threshold, method version or config version differs from request; fail |
| method_sampling_mismatch | Method counts or sampling/split seeds differ from request; fail |
| method_unavailable | Method claim/context supplied where no method result was shown; fail |
| method_execution_error | Method-direction claim cites an execution failure; fail |
| method_threshold_unconfigured | Method-direction claim cites a result with no configured threshold/decision; fail |
| method_direction_mismatch | Method attribution differs from the saved configured decision; fail |
| rows_unavailable | Row claim where no displayed rows exist (E1); fail |
| row_unavailable | Row index outside the displayed sample; fail |
| row_value_mismatch | Quoted A/B row values differ; fail |
| summary_unavailable | Summary claim where no summary was shown; fail |
| statistic_unavailable | Requested optional summary statistic was not supplied; fail |
| summary_value_mismatch | Statistic value or scalar/vector shape differs; fail |
| method_claim_consistent | Method citation matches saved configured decision; pass finding |
| row_claim_consistent | Row citation matches saved displayed values; pass finding |
| summary_claim_consistent | Statistic citation matches saved summary; pass finding |
| claim_binding_unverified | Citation locally matches, but relevant original evidence/method bindings are missing or contradictory; abstain finding |

Schema-invalid context is a caller/storage error and raises ValidationError,
rather than inventing a trusted identity or interpreting evaluator metadata.
Nonfinite/cyclic/non-JSON objects bypassing typed construction are likewise
outside the callable contract; load typed records using normal validation.

## Examples, tests and separate adversarial review

`examples/track_b_phase2.jsonl` contains full typed inputs, contexts and outputs
for passing, failing and abstaining cases. Fixture requests are independently
constructed from fixed mock samples/configuration. These are process examples,
not natural-error or causal-accuracy observations.

- Pass/release: E4 ANM favors A_to_B, S1 chooses B_to_A while correctly citing
  A_to_B. Qualified disagreement is allowed.
- Fail/no release: same evidence, S1 claims ANM favors B_to_A.
- Checker abstain/no release: otherwise valid E4, independent method request missing.
- Pass/no release: valid cached S1 abstention.

Focused unit tests cover E1–E4, row/summary vocabulary, invalid references,
unsupported probability fields, exact numeric citations, method states, qualified
disagreement, missing trust records, unchanged S1, deterministic repeated checks,
zero model/ANM/network calls, and rejection of evaluator fields.
`tests/test_prediction_process_injections.py` separately holds deliberate stale
sample/config/split, swapped mapping, missing/forged result, replacement S1 and
invalid-ANM-state injections. None is scored as naturally occurring prediction error.

A separate adversarial self-review followed implementation (no extra agent or
LLM verification layer). It checked false releases/rejections, cache/provenance
binding, claim order, threshold/schema bypasses and mutability. Confirmed defects
were reproduced before fixes:

1. An earlier false claim downgraded later correct claims. The regression failed,
   then passed after separating receipt binding from accumulated claim failures.
2. model_copy could hide undeclared probability/evaluator fields from model_dump.
   Four regressions first falsely released (prediction, claim, evidence, method),
   then passed after recursive record snapshots preserved fields for revalidation.

## Remaining limitations and roadmap deviations

- Trusted cache provenance/authentication is Kris's responsibility. Hashes do
  not authenticate a dishonest receipt; changing every original/candidate record
  together cannot be detected by a local consistency checker.
- Anish must ensure original request digests actually describe the sample,
  orientation and frozen configuration executed. The checker does not run ANM,
  validate sample contents, inspect preprocessing or resolve reproducibility_ref.
- Opaque IDs cannot reveal a semantically swapped variable mapping if the producer
  consistently mislabeled it before all records were saved. Sanitization of
  permitted labels/units/reasons/warnings and randomization independence remain
  producer obligations. Schemas reject evaluator keys but cannot detect hidden
  gold information disguised as allowed strings.
- No accuracy, coverage/yield or ANM-only/simple-gate evaluation is implemented.
  Section 7 requires weighted coverage, correct/wrong yield, selective accuracy,
  process-error rate and paired source-group uncertainty from the runner/scorer.
  S2 only filters cached S1: correct and wrong yields cannot increase through
  this gate. Report correct answers sacrificed along with wrong answers removed.
- No new Phase 1 claim types or prediction/evidence fields were necessary.
  New verifier-only context/request contracts are required to avoid trusting
  result-copied digests. Exact sample/config bytes and version formats still
  need teammate agreement. The request route avoids adding a resolver/storage layer.
- Existing `causalbridge.verifier` layout is preserved; Track A contracts and
  Phase 1 predictor remain unchanged. No scientific deviation from V2: only
  deterministic structured checks are implemented, with explicit abstention
  when original evidence provenance is unavailable.

## Reproduction

```bash
uv run pytest tests/test_prediction_checks.py tests/test_prediction_process_injections.py -q
bash scripts/check.sh
```

Baseline: 164 tests passed before Phase 2. Final `bash scripts/check.sh` passed:

- **241 tests passed** (77 new: 54 verifier unit/adversarial/example tests and
  23 separate deliberate process-injection cases).
- Ruff lint and format checks passed.
- Existing eight-case Track A scripted demo passed.
- Source distribution and wheel built successfully.
- Overall statement coverage: 92%; checks.py: 98%; bindings.py: 97%.
- All four saved Phase 2 examples reproduce their exact expected check outputs.
- Checksum comparison against the pre-Phase-2 snapshot confirms all pre-existing
  source files except verifier/checks.py, plus every exported schema, are unchanged.
- No changes are committed or pushed.

Exact Phase 2 file changes:

- Modified: `src/causalbridge/verifier/checks.py`, `tests/conftest.py`,
  `tests/test_direction.py`.
- Added: `src/causalbridge/verifier/bindings.py`, `tests/test_prediction_checks.py`,
  `tests/test_prediction_process_injections.py`, `examples/track_b_phase2.jsonl`,
  `docs/track_b_phase2.md`, `docs/plans/track-b-phase2.md`.
