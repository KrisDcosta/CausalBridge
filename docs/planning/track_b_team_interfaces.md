# CausalBridge: Track B team interfaces

**Status:** Working integration contract, prepared from teammate messages and the revised November 8, 2026 CausalBridge implementation roadmap.

**Primary use:** Phase 1 typed schemas, mock prediction adapter, and subsequent V2 verifier integration.

**Ownership:** Vaishak defines the initial Track B contracts; Kris and Anish may propose compatible revisions during integration.

> **Read this first:** Sections marked **Confirmed** capture statements teammates explicitly supplied. Sections marked **Proposed** are initial choices for implementation, not agreed API guarantees. In particular, the example predictor request/response previously shared in the group was preliminary and must not be treated as the final Track B contract. Keep all changes to Track B additive; preserve Track A's existing `RuntimeCase`/CPT v1.0 interfaces.

## 1. Scientific and architectural boundaries

Track A and Track B are distinct tasks.

- **Track A (known graph):** Given a supplied causal DAG and supporting evidence, determine what a graph or numerical operation justifies. In particular, structural connectivity alone cannot certify the sign or magnitude of an effect. Keep the existing parser, reference implementation, tools, and verifier intact unless a demonstrated issue requires a change.
- **Track B (unknown direction):** Predict which direction is more plausible, `A_to_B` or `B_to_A`, using one of four evidence conditions. Permit abstention. Evaluate agreement with imperfect reference directions separately from whether a prediction's *claims about its evidence* are truthful.
- **S0/S1/S2:** S0 and S1 are distinct model prompt conditions applied to the same supplied evidence. S2 is a deterministic release/check decision over the **saved S1 proposal**, with **no additional LLM call** and no fresh ANM calculation. Kris owns prompting, caching, and the shared runner.
- **Checker boundary:** A `pass` does **not** verify that the inferred causal arrow is true. The checker may validate inputs, provenance, citations, method attribution, internal consistency, and typed overclaims. It must permit a qualified prediction that disagrees with ANM while describing ANM accurately.
- **No reference-label leakage:** Gold directions, pair metadata used for scoring, dataset weights, source groups, and raw evaluator-only descriptions must not be passed to the predictor, verifier, or ANM calculation.
- **No new training or multi-agent system** is required. Use one bounded ANM diagnostic; do not replace it with a suite of discovery methods.

## 2. Team ownership and handoffs

| Owner | Responsibility under the roadmap | Interface relevant to Vaishak |
|---|---|---|
| **Vaishak** | Audit/preserve existing implementation; typed Track B direction predictor; evidence/method binding and claim checker (V1/V2) | Defines typed request, prediction, check result, and mock fixtures; exposes callable functions to runner |
| **Kris** | E1–E4 evidence packaging, S0/S1 prompts, caching, shared runner | Supplies runtime evidence packages, prompt condition, and saved proposal to checker; records trace and release result |
| **Anish** | Numerical inference, ANM regression/HSIC diagnostic, method controls | Supplies typed method result and provenance; independently checks Track A witness calculations |
| **Faizah** | Tübingen ingestion and metadata audit, evaluator-only labels, scoring, bootstrap intervals | Provides opaque case identifiers and evaluator join keys; ensures no label leakage |
| **Arunima** | Structural DAG algorithms, witness fixtures, graph checks, research design | Supplies Track A witness/graph fixtures; preserves existing schema compatibility |

**Integration rule:** Implement with stable mock fixtures now; adapt at module boundaries when real teammate implementations arrive. Do not implement teammates' assigned algorithms or pipelines as a dependency workaround.

## 3. Track A format and merged work (confirmed)

Arunima reports that PR [#1](https://github.com/mvaishak/CausalBridge/pull/1) adds a DAG/CPT generator, structural graph utilities, and an initial witness validator, following the repository's existing `RuntimeCase`/CPT **v1.0** schema. The PR was merged into `main` according to the repository check on November 14, 2026.

- `graph_nodes`: all node identifiers, including isolated nodes, as unique strings.
- `graph_edges`: ordered `[source, target]` directed pairs.
- Each CPT: `node`, `parents`, and `p_one`, with `p_one` mapping a binary parent assignment to `P(node=1)`.
- Generated CPT `parents` are alphabetically sorted; assignments use `0`/`1` in that parent order. For `parents=["X","Z"]`, `"01"` means `X=0, Z=1`.

**Confirmed example (M+):**

```json
{
  "graph_nodes": ["X", "Y", "Z"],
  "graph_edges": [["Z", "X"], ["Z", "Y"], ["X", "Y"]],
  "cpts": [
    {"node": "Z", "parents": [], "p_one": {"": 0.5}},
    {"node": "X", "parents": ["Z"], "p_one": {"0": 0.2, "1": 0.8}},
    {"node": "Y", "parents": ["X", "Z"], "p_one": {"00": 0.6, "01": 0.1, "10": 0.9, "11": 0.4}}
  ]
}
```

This is the **graph/CPT portion**, not necessarily a complete serialized `RuntimeCase`. Exact executable cases are in `tests/test_benchmark_generator.py`, `witness_models()`.

The planned witness pair has the same observed joint distribution, `P(X=x,Y=y)=0.25` in every cell, but intervention effects `+0.30` and `-0.30`. Arunima reports witness tests passing; **Anish's independent numerical confirmation remains a separate requested check**. Full witness models and hidden evaluator data must not enter Track A runtime prompts or tool inputs.

## 4. Track B evidence conditions (confirmed by roadmap; Kris payload pending)

Kris has not yet provided an exact machine-readable package schema. The November 8 roadmap specifies:

| Package | Model-visible evidence | Comparison |
|---|---|---|
| `E1` | Sanitized variable names and units, no sample rows | Semantic/world-knowledge signal |
| `E2` | Anonymous `A`/`B` variables, selected observation rows and numeric summary | Data-only signal |
| `E3` | Exactly the same numeric observations/summary as E2 **plus** sanitized variable names and units | E2 versus E3 isolates added names |
| `E4` | E3 evidence **plus one cached ANM diagnostic and limitations** | E3 versus E4 isolates method evidence |

Additional constraints:

1. Use the fixed question: **“Which direction is more plausible, A → B or B → A? You may abstain.”**
2. A/B orientation is assigned by a recorded random seed independently of the reference direction, and remains identical across packages for the same case.
3. A numerical prompt may initially show up to approximately 64 selected rows; ANM may use up to approximately 256 rows. These are pilot defaults, not confirmed final sample sizes.
4. E2 and E3 must share the same numeric sample identity; their *whole-package* identities differ because E3 reveals names.
5. ANM's sample may be larger than displayed rows. Track separate identities and sizes for the displayed rows and method-input sample.
6. Evidence records and prompts must be sanitized of evaluator-only metadata.

**Proposed:** Represent a single request as one package, not `evidence_refs: ["E1","E2"]`. E1–E4 are experimental conditions, not cumulative reference IDs. Use opaque `case_id` and explicit `package` fields.

## 5. Anish's ANM specification (confirmed)

### 5.1 Algorithm and score semantics

The diagnostic fits regressions in both directions on training rows and measures residual dependence on held-out rows. Lower residual dependence favors a direction **under ANM assumptions**.

- `score_ab`: HSIC between **A** and the held-out residuals of predicting **B from A**.
- `score_ba`: HSIC between **B** and the held-out residuals of predicting **A from B**.
- `margin = score_ba - score_ab`.
- A **positive** margin favors `A_to_B`; a **negative** margin favors `B_to_A`.
- `tau >= 0` is selected on development data and frozen before held-out evaluation.

| Condition | Decision | Predicted direction |
|---|---|---|
| `margin > tau` | choose A → B | `A_to_B` |
| `margin < -tau` | choose B → A | `B_to_A` |
| `abs(margin) <= tau` | abstain | `null` |
| Threshold not yet configured | report scores without a directional decision | `null`; reason `threshold_not_configured` |

A valid ambiguous margin is an **abstention, not an execution error**. HSIC scores and their margin are **not causal probabilities** or proof of causation. An ANM-favored direction may be contradicted by another justified source of evidence; the LLM may disagree if it represents the method result honestly.

### 5.2 Result and failure behavior

**Successful calculation:** `status: ok`, both scores, margin, threshold if configured, decision, predicted direction (nullable), and a reason code. If threshold is not configured, scores may exist without a direction decision and `reason_code: threshold_not_configured`.

**Execution failures:** `status: error`, stable reason code, no direction, for:

- Invalid shape, nonnumeric inputs, or nonfinite values.
- Too few rows, constant columns, or insufficient variation.
- Invalid method configuration.
- Regression fitting failure.
- Undefined kernel bandwidth or invalid HSIC result.

Do not invent a final enum of all error reason-code strings before Anish supplies them. Model the broad error categories and tolerate only declared/recognized codes once the interface is frozen.

### 5.3 Evidence binding and provenance (confirmed as information to include or reference)

**Sample:**

- Sample digest and A/B column mapping.
- Counts for selected, training, and evaluation rows.
- Sampling seed and train/evaluation split seed.
- Validation findings and input-quality warnings.

**Preprocessing:**

- Transform per variable.
- Training-set standardization means and scales.
- Residual-scaling rule.
- Explicit record of any diagnostic-specific evaluation transform.

**Method configuration:**

- Regression method, kernel, hyperparameters.
- HSIC estimator, bandwidth rule, score convention.
- Abstention threshold and threshold/configuration version.
- Method version and configuration digest.

Detailed row indices and dependency versions may stay in a linked reproducibility record identified by reference(s). **No gold direction or evaluator labels** may enter the diagnostic.

### 5.4 Checks Vaishak may implement

- Verify that the method-result sample digest, A/B orientation, and configuration identifiers match the evidence/tool request used for that run.
- For `status: ok` with configured threshold, recompute `margin` and direction/abstention from the saved scores and threshold, with a documented floating-point tolerance.
- Verify that a model claiming “ANM favors A → B” accurately quotes the saved result; similarly for B → A and abstention.
- Reject claims of ANM support when no method result is available, or when a result is an error/unconfigured.
- Reject claims that raw HSIC scores/margins are calibrated causal probabilities.
- Permit a **qualified disagreement** with the method when the model accurately describes its output and limitations.

## 6. Proposed Track B contracts for Vaishak to implement

These are **initial schemas** for Codex to refine against existing Pydantic conventions. They are deliberately separate from the known-graph `effect_direction` task: `A_to_B` / `B_to_A` identify a **hypothesized arrow between two variables**, not positive/negative/zero effect sign.

### 6.1 `DirectionEvidence` (proposed)

Suggested fields:

- `case_id: str`: opaque runtime identifier.
- `package: Literal["E1", "E2", "E3", "E4"]`.
- `task: Literal["causal_direction"]`.
- `variable_labels: tuple[str, str] | None`: absent/anonymous where not allowed by evidence condition.
- `units: tuple[str | None, str | None] | None`.
- `display_rows: list[tuple[float, float]] | None`.
- `summary: ... | None`: numeric summary with counts and defined provenance.
- `ab_mapping_id`, `display_sample_digest`, `package_digest`: computed from canonical, specified inputs.
- `method_result: ANMResult | None`: E4 only.
- `method_sample_digest` and method sample counts must either be in `method_result` or an immutable associated provenance record.

**Rules:** E1 cannot contain numeric rows or a method result; E2 cannot reveal variable names; E3 cannot contain an ANM result; E4 includes the ANM diagnostic/status and its stated limitations. The model-visible view must omit evaluator-only metadata. Decide canonical digest format and whether evidence IDs are embedded or supplied via a registry before integration.

### 6.2 `ANMResult` (proposed mapping of confirmed semantics)

```json
{
  "status": "ok",
  "score_ab": 0.012,
  "score_ba": 0.035,
  "margin": 0.023,
  "threshold": 0.01,
  "decision": "A_to_B",
  "predicted_direction": "A_to_B",
  "reason_code": null,
  "sample_digest": "sha256:EXAMPLE_METHOD_SAMPLE",
  "ab_mapping_id": "mapping-001",
  "selected_row_count": 256,
  "training_row_count": 192,
  "evaluation_row_count": 64,
  "sampling_seed": 261,
  "split_seed": 261,
  "config_digest": "sha256:EXAMPLE_CONFIG",
  "method_version": "ANM-EXAMPLE",
  "reproducibility_ref": "repro-001",
  "limitations": ["Unmeasured confounding cannot be excluded"]
}
```

**Illustrative example only.** Hashes, counts, threshold, and method version are placeholders. The final transport contract must additionally preserve the agreed preprocessing and configuration details or link to immutable records containing them. Anish's final field names are not yet confirmed. In an unconfigured-threshold case, `threshold` and `decision` should be nullable, with `reason_code: threshold_not_configured` and `predicted_direction: null`.

### 6.3 `DirectionPrediction` (proposed)

```json
{
  "case_id": "D0042",
  "predicted_direction": "A_to_B",
  "abstained": false,
  "reason_code": null,
  "claims": [
    {
      "type": "method_direction",
      "evidence_ref": "method_result",
      "direction": "A_to_B"
    }
  ]
}
```

**Rules:** `predicted_direction` is `A_to_B`, `B_to_A`, or `null`; a null direction must be consistent with abstention. The predictor does **not** produce ANM's `score_ab`, `score_ba` or causal probabilities. Typed claims may reference available displayed rows/summaries/method output. The final claim vocabulary should be intentionally small and checkable. Preserve the raw model reply and parse failure outside the model-generated fields in an execution trace.

### 6.4 `PredictionCheck` (proposed)

Suggested fields:

- `status: Literal["pass", "fail", "abstain"]` (subject to runner agreement).
- `release: bool`: whether saved S1 prediction may be released.
- `reason_codes: list[str]`: stable machine-readable rule identifiers.
- `claim_findings: list[...]`: optional typed per-claim findings.
- `case_id`, `package_digest`, `proposal_digest`: bind the check to the exact cached proposal and evidence.
- `checker_version`: provenance for reproducibility.

A verifier `pass` is a **process/evidence-consistency result**, never proof that the causal direction is correct. Decide whether S1's own abstention maps to `pass` with `release=false` or a separate `abstain` status; freeze this distinction before scoring. A check must never silently rewrite an S1 directional answer into the opposing direction.

### 6.5 Intended callable boundaries (proposed)

Exact Python signatures and module locations should follow existing package layout:

```python
# Proposed interface only, not current repository code.
predict_direction(evidence: DirectionEvidence, prompt_condition: str, model_client) -> PredictionExecution
check_prediction(evidence: DirectionEvidence, saved_prediction: DirectionPrediction) -> PredictionCheck
```

`PredictionExecution` is a trace envelope containing the raw response, parsed proposal or parse failure, model settings, usage, latency, and provenance. The **runner**, not the predictor, owns S0/S1 prompt templates, case scheduling, persistence, and cache lookup. The **runner** calls the checker on **cached S1 output** to compute S2.

## 7. Required checks and test fixtures

### 7.1 Minimum happy-path fixtures

1. E1 names-only prediction without claiming numerical support.
2. E2 anonymous observations and summary; no label leakage.
3. E3 same observation identity as E2 plus permitted labels/units.
4. E4 valid method result and correctly attributed method-direction claim.
5. E4 valid **qualified disagreement**: method favors `B_to_A`, model tentatively chooses `A_to_B` but attributes the method accurately.
6. Valid abstentions from LLM and ANM, including ANM tie/ambiguous result and threshold not configured.

### 7.2 Negative and boundary fixtures

- Malformed response, extra fields, invalid direction, contradictory `abstained` and `predicted_direction`.
- Cross-case/cross-package or stale method digest; swapped A/B orientation.
- E3 claiming to have used E4's ANM; E1 claiming to cite numeric rows.
- Claim citing a row or summary not actually displayed or permitted.
- False method-direction claim; fabricated method result; treating ANM's margin as a probability.
- Invalid ANM result: missing scores, incoherent margin, threshold/decision mismatch, error status with a direction.
- Unconfigured threshold with valid scores and **no** fabricated decision.
- No gold labels, source weights, or evaluator-only descriptions in model or checker inputs.
- `check_prediction` does not mutate saved S1 output and makes **zero** LLM/ANM calls.
- Injected process-corruption results are logged separately from naturally occurring prediction errors.

Preserve existing Track A tests as regression tests. Use mock ANM outputs before Anish's live method arrives. Record explicit reason codes for every verifier rejection.

## 8. Runner integration assumptions for Kris (proposed, awaiting confirmation)

Kris asked for the predictor input/output and the verifier call on a saved prediction. The intended handshake is:

1. Runner constructs and persists a runtime-safe **single E1/E2/E3/E4 evidence package**, with opaque case ID, A/B mapping and defined evidence IDs.
2. Runner invokes `predict_direction` once for S0 and once for S1, using its own S0/S1 prompt configurations, and saves the raw responses and parsed outputs even on failures.
3. Runner invokes `check_prediction` over **exactly the cached S1 proposal** and matching evidence to obtain S2. No new LLM call, no fresh ANM invocation, no regeneration of the original prediction.
4. Runner logs package/condition, trace and proposal IDs, model settings, tokens/cost, failure stages, check result, release decision, and stable reason codes.
5. Evaluator joins reference directions and weights **after execution**; predictor/verifier do not receive evaluator records.

**Remaining integration choices:** Final method/runner function names; whether prompts are passed as templates or preformatted requests; digest canonicalization; location of full method reproducibility records; exact checker `abstain`/`pass` semantics; and final stable reason-code enum. These can be resolved by adapters without blocking the mocked Phase 1 implementation.

## 9. Scoring implications (roadmap requirement)

Evaluation is owned by Faizah and the shared runner, but the checker must emit complete status data to support:

- Weighted coverage.
- Weighted correct-answer yield and wrong-answer yield.
- Weighted selective accuracy (undefined when no prediction is released).
- Process-error rate.
- Runtime/cost/failure accounting.
- Accuracy-versus-coverage tradeoff and a simple evidence-availability/input-validity gate baseline.

**Important invariant:** On identical cases, with a pure S2 release gate applied to saved S1 outputs and no rewritten predictions, S2's correct-answer yield and wrong-answer yield **cannot exceed** S1's corresponding yields. Measure wrong answers removed **and** correct answers sacrificed. Never claim a gain in absolute correct-answer yield from filtering alone.

## 10. Phase 1 implementation order for Codex

1. Inspect repository state after merged PR #1; run existing tests and record baseline. Do not assume the reported test count matches the current checkout.
2. Preserve Track A `RuntimeCase`/CPT v1.0 and existing parser/verifier behavior; inventory reusable JSON parser, model client, transport, and logs.
3. Add strict Track B typed records with explicit *proposed* field names and mock fixtures for E1–E4 and ANM states.
4. Implement a **single-call** typed direction predictor reusing the existing model transport/parser. Do not reuse Track A's three-call parse/plan/interpret pipeline for this fixed question.
5. Establish the checker-result interface only in Phase 1; implement full method/evidence/claim checks in Phase 2.
6. Test parse and schema failures, abstention, provenance placeholders, and runtime/evaluator separation; run all existing Track A tests.
7. Share concrete mock JSON requests/results and callable signatures with Kris and Anish for integration adjustments. Document every deviation from the roadmap.

## 11. Source precedence and open decisions

**Source precedence for implementation:** (1) November 8 detailed roadmap for research and ownership; (2) teammates' explicit ANM/Track A conventions; (3) this document's proposed API choices; (4) preliminary group-chat examples. The high-level plan controls overall scope. If exact field names remain unsettled, prefer a thin adapter over a breaking Track A refactor.

**Open decisions to record, not block on:**

- Final exact Kris E1–E4 payload schema and S0/S1 prompt/runner signatures.
- Final exact Anish ANM request/result field names, stable error codes, threshold/config version format and provenance location.
- Canonical bytes/serialization for sample/package/config digests and A/B mapping identifier.
- Typed claim vocabulary and policy for verifier abstention versus failed checks.
- Final model runtime availability, pilot sample counts, and production runtime configuration.

The team can change provisional Track B fields during integration; each change should be accompanied by a representative JSON fixture and a regression test.
