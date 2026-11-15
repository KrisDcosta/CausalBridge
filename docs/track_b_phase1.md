# Track B Phase 1 handoff

Implemented against the November 8 detailed roadmap, with ANM conventions from
`planning/track_b_team_interfaces.md`. Track A RuntimeCase/CPT v1.0, graph tools,
parser, model transport, orchestration, CLI and verifier remain unchanged from
merged PR #1 (`7a47465`). The only checkout update was a fast-forward to that PR.

## Callable boundary

```python
from causalbridge.discovery.schemas import DirectionEvidence, PromptCondition
from causalbridge.llm.client import OllamaModel
from causalbridge.llm.predictor import predict_direction
from causalbridge.verifier.checks import check_prediction

evidence = DirectionEvidence.model_validate(runtime_payload)
condition = PromptCondition(
    condition_id="S1",
    version="kris-dev-1",
    instructions=runner_prompt_text,
)
execution = predict_direction(evidence, condition, OllamaModel())
# Persist the complete execution, including failures, before doing anything else.
if execution.failure_stage is None:
    saved_s1 = execution.prediction
    check = check_prediction(evidence, saved_s1)
```

`predict_direction(evidence, prompt_condition, model_client) -> PredictionExecution`
uses the existing `JSONModel.generate(messages, schema)` once and the existing
strict `parse_json`. No tool routing, ANM execution, retry, cache, persistence,
prompt-condition selection or evaluator join occurs inside the predictor.
The runner supplies condition ID, version and instructions; a fixed question
and shared output-format/evidence caveats are appended for all conditions.

The trace holds the evidence snapshot, package/display IDs, exact messages,
output schema, prompt digest, condition, optional ModelConfig, Generation
(raw text/model/token usage/generation latency), parsed prediction, failure
stage/error, total latency and run ID. Unknown token counts remain null in
Generation. No fabricated usage, probabilities or cost estimates are emitted.
Failures have stages `generate`, `parse`, or `binding`. A parsed but misbound
prediction remains in the trace for audit; **do not use it when failure_stage
is non-null**. Malformed replies remain in Generation.text. Input validation
errors raise before generation.

`check_prediction(evidence, saved_prediction) -> PredictionCheck` is deliberately
a non-releasing placeholder. Every call returns `status="abstain"`,
`release=false`, `reason_codes=["checker_not_implemented"]`, bound to the
supplied evidence package and proposal digest. It does not mutate S1, call a
model/method, check claim truth, certify bindings or judge causal correctness.
No S2 scientific evaluation is valid with this placeholder. Phase 2 will check
the saved proposal, not regenerate it or replace its arrow.

## Runtime schemas

All records inherit the existing frozen `Record` with forbidden extra fields.
Unknown evaluator fields are rejected, including in nested records; there is no
benchmark projection helper that silently accepts dataset metadata.

`DirectionEvidence` requires opaque case ID, single E1/E2/E3/E4 package,
opaque A/B mapping ID and explicitly recorded mapping seed:

| Package | Required/permitted contents |
| --- | --- |
| E1 | Sanitized labels, optional units; no rows, summary, sample seed or ANM |
| E2 | Anonymous A/B rows, summary and display sampling seed; no names/units/ANM |
| E3 | E2 numeric evidence plus sanitized labels and optional units; no ANM |
| E4 | E3 evidence plus one cached ANMResult (including error/unconfigured states) |

Summary fields are a fixed numeric vocabulary: n_display, optional A/B mean,
std, minimum, maximum and correlation. Its source is `display_rows`; n_display
must match the rows. Statistical accuracy remains the producer's responsibility
(no new summary algorithm). Rows and numeric fields must be finite. The
64/256 sample sizes are pilot defaults, not hard constraints; two-row demo
fixtures illustrate transport only and are not valid pilot evidence by themselves.

`DirectionPrediction` contains case_id, package_digest, predicted_direction
(`A_to_B`, `B_to_A`, null), abstained, reason_code and typed claims. Null direction
requires abstained=true and a reason. No numeric LLM confidence or score fields.
Claims currently describe method direction, exact displayed row values (zero-based
index), or one summary statistic. They are typed assertions, **not validated
evidence use**. A model can honestly report an ANM preference and choose the
opposite direction; this is structurally valid qualified disagreement.

`PredictionCheck` contains status (pass/fail/abstain), release, stable reason
codes, typed per-claim findings, case/package/proposal IDs and checker version.
Only pass may release. Phase 1 always abstains. The policy for S1's own abstention
and the final claim-check reason-code vocabulary remain Phase 2 decisions.

## ANM semantics and provenance

`score_ab` is held-out residual dependence of A with residuals predicting B;
`score_ba` is the reverse. `margin=score_ba-score_ab` is checked using
`math.isclose(rel_tol=1e-9, abs_tol=1e-12)`. No nonnegative HSIC constraint is
invented because estimator conventions are not frozen. All values must be finite.

For configured nonnegative threshold tau, margin > tau chooses A_to_B,
margin < -tau chooses B_to_A, and equality/inside the band yields decision
`abstain`, predicted_direction=null, reason `ambiguous_margin`. Threshold
comparisons use the recomputed saved-score difference strictly; the tolerance
applies only to validating the reported margin. This prevents a tiny reporting
discrepancy from creating a direction when the scores tie. Save thresholds with
full float precision: near a boundary, binary floating-point subtraction may
differ from a rounded decimal margin. A directional decision has reason_code=null.
An unconfigured threshold requires null decision/direction and
`threshold_not_configured`, while retaining valid scores. Ambiguity is status=ok.

Errors require status=error, no scores/margin/decision/direction, a nonempty
reason_code and broad category: input_validation, configuration, regression or
dependence. Specific teammate error codes remain open strings until agreed;
this does not claim to recognize a frozen enum. Threshold may be retained on
error for reproducibility. Every result must carry nonempty limitations.

ANMProvenance carries sample digest, A/B mapping, selected/training/evaluation
counts, sampling/split seeds, config digest/version, method version, validation
findings and quality warnings. Counts must partition selected rows; successful
results require nonempty train and evaluation subsets. It also requires a
content-addressed immutable `reproducibility_ref`. The linked record must retain
per-variable transforms, training-only means/scales, residual scaling, evaluation
transform, regressor/kernel/hyperparameters, HSIC estimator/bandwidth/score
convention and threshold version. Row indices and dependencies may be linked.
Phase 1 validates reference syntax, not record availability or authenticity.

## Identities and leak boundary

`canonical_digest` is `sha256:` plus SHA-256 of UTF-8 Python json.dumps with
sort_keys=true, separators=(",",":"), ensure_ascii=true, allow_nan=false.
Sequence order matters; hash validated model JSON to normalize numeric types.
This is a provisional Python canonicalization convention, not RFC 8785.

- `display_sample_digest`: mapping ID/seed, display rows and display sampling
  seed; excludes names, package and summary. E2/E3/E4 must be matched by the
  runner; equal numeric evidence has equal display identity despite names.
- `package_digest`: the entire validated runtime package, including summary,
  permitted names and cached method status/provenance. Changing any field changes it.
- `ANMProvenance.sample_digest`: independent identity of method-input observations
  and A/B mapping, supplied by Anish's adapter. It need not equal the displayed
  sample identity. The demo hashes `{ab_mapping_id, rows}` for method samples;
  production method/config digest bytes must be frozen with Anish.
- `proposal_digest`: the exact validated DirectionPrediction; checker binds to it.
- `prompt_digest`: exact outgoing message sequence, including runner instructions.

Digest properties are computed, not accepted as caller-controlled evidence
fields. Persist the computed IDs beside serialized evidence (the trace does this).
Hashes detect changes, not provenance authenticity. Independent method-sample/
configuration binding against the original ANM request belongs in Phase 2;
only mapping compatibility and internal ANM arithmetic are enforced now.

No reference directions, dataset IDs, source groups, weights or evaluator blobs
are accepted. Opaque IDs, sanitized labels, units, prompt instructions and method
prose remain producer trust boundaries: a schema cannot detect gold information
deliberately disguised as permitted strings. Mapping seeds must be chosen without
reference labels; the predictor cannot establish randomization independence.

## Offline demonstration and examples

```bash
uv run python -m causalbridge.discovery.demo > /tmp/track-b-demo.jsonl
uv run pytest tests/test_direction.py -q
bash scripts/check.sh
```

The seven demo records contain exact inputs, execution traces, placeholder
checks and mock reproducibility records. `examples/track_b_phase1.jsonl` keeps
compact request/prediction/check versions for review. All are scripted fixtures,
not empirical LLM/ANM runs. Generate JSON Schemas with each model's existing
Pydantic `model_json_schema()` method; Track A CLI exports stay unchanged.

## Unresolved integration assumptions and deviations

- Provisional Track B schema version 0.1 and exact field names await Kris/Anish
  review. Keep any teammate naming adapter at the module boundary.
- Kris owns E1–E4 construction, paired rows/orientation, S0/S1 prompts, caching,
  experiment scheduling and persistence. Neither a packager nor runner is added.
- Anish owns actual method execution, configuration versions, threshold selection,
  final error codes and immutable reproducibility storage/resolution. No ANM added.
- Faizah owns ingestion, evaluator metadata joins and scoring. None added here.
- The roadmap's top-level module sketch is nested inside the existing
  `causalbridge` package. The existing parser is reused from a separate
  `llm/predictor.py`; Track A's three-call pipeline is not adapted or rewritten.
- Full evidence/claim checking from roadmap V2 is intentionally deferred by the
  requested Phase 1 scope. Arithmetic and schema checks are input validation,
  not a claim verifier. Check status/release policy still needs runner agreement.
- Live model availability and final sample sizes were not tested or decided.

## Verification record — 2026-11-14

- Merged-PR baseline: 102 tests passed.
- New Track B tests: 62 passed; all-suite total: **164 passed**.
- `bash scripts/check.sh`: Ruff lint/format passed, pytest passed (91% overall
  statement coverage), eight-case existing Track A demo passed, sdist/wheel built.
- Offline Track B demo: seven records, zero prediction failures; every checker
  result explicitly non-releasing. Mock HTTP test confirms one Ollama request.
- Independent review found two issues, both reproduced with failing tests and
  fixed: tolerance must not invent a direction from tied scores, and the
  unconfigured mock needs threshold-consistent configuration/reproducibility hashes.
- `git diff --exit-code 7a47465` for Track A schemas, pipeline, parser, transport,
  verifier and exported schemas passed; these files are unchanged.
