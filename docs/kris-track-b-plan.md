# Kris: Track B working plan

Status: proposed integration design, 12 November 2026. Repository inspected at
`042d5589e2db25706337cc2112e0ce347c11b247` on `main`. Planning sources: the
8 November high-level plan and implementation roadmap, and the collaboration
document last modified 11 November. Proposed APIs below do not exist yet and need
review by affected owners.

## Repository audit

The repository implements Track A, the original known-DAG workflow. Track B is
absent. The roadmap's proposed `src/discovery/...` paths must be adapted to the
actual importable package, `src/causalbridge/`.

| Component | Actual implementation | Reuse decision |
| --- | --- | --- |
| Transport | `llm/client.py`: `JSONModel.generate(messages, schema) -> Generation`; Ollama implementation, configuration and usage accounting | Reuse for Track B |
| Parsing | `llm/parser.py`: `parse_json(text, model)` rejects duplicate keys and extra fields through typed models | Reuse parser; create new prompts |
| Shared record base | `schemas.py`: `Record`, extra fields forbidden, nonfinite values rejected | Reuse base; new Track B types |
| Track A input | `RuntimeCase`, mandatory DAG, binary CPT/joint evidence | Keep; unsuitable for continuous unknown-direction pairs |
| Track A answer | `Query.effect_direction` means positive/negative/zero effect | Keep; never overload with A-to-B/B-to-A |
| Pipeline | `CausalBridge.run(case, query=...)`, up to three model calls: parse, plan, interpret | Use for Track A; separate Track B execution path |
| Verifier | Bound known-graph operation, evidence prerequisites, trusted tool-result consistency | Preserve; Track B needs process checks with different claims |
| Reference backend | Exact enumeration capped at 12 binary nodes; structural/backdoor utilities | Useful Track A development backend; no ANM |
| CLI | `demo`, `run`, `schemas` | Add a distinct Track B command later |
| Evaluation/benchmark | Package placeholders | Runner, baselines, scoring and datasets still pending |
| Tests/CI | Ruff, pytest/coverage, eight-case offline demo, package build | Run unchanged before and after new work |

Documentation still describes original A–E conditions, graph-group splits and
the old ownership table. The revised E1–E4/S0–S2 protocol is the planning target;
the existing docs are accurate about current code, not the new experiment.
No live-model quality or real-data performance is established by the fixture demo.

Baseline verification on 12 November 2026, Python 3.12.13:
`UV_CACHE_DIR=/tmp/causalbridge-uv-cache bash scripts/check.sh` passed. Results:
67 tests, 88% coverage, Ruff lint/format passed, eight demo traces (four verified,
three unsupported, one wrong operation), source distribution and wheel built.
The temporary cache override was necessary because the default cache path was
not writable. No source changes were needed to pass.

## Research role

Kris controls the experimental inputs and execution. This makes the comparisons
interpretable: E2 versus E3 changes semantics only; E3 versus E4 adds method
evidence only; S0 versus S1 changes instructions only; S1 versus S2 changes release
decisions on the exact same saved proposal. Faizah joins labels after execution.

| Owner | Input to Kris / output from Kris |
| --- | --- |
| Faizah | Audited eligible pairs, sanitized names/units and runtime rows; separate evaluator mapping, source groups, weights and splits. Receives complete traces and failure records. |
| Anish | ANM result bound to the selected A/B data, with scores, configuration and sample provenance. Receives label-free numeric inputs only. |
| Vaishak | Direction predictor/checker contracts. Receives proposed runtime packages and returns structured proposals/check results. Kris reviews integration. |
| Arunima | Study-design and witness context; reviews related data/design questions. Track A remains a separate task. |

## Runtime and experiment records

Maintain three separate layers:

1. Evaluator record: original pair ID, original-to-A/B mapping, reference direction,
   source group, weight, split, raw descriptions and original row indices. Never
   serialize this into model messages or ANM inputs.
2. Public evidence: opaque case ID, package, fixed question, A/B variables,
   allowlisted names/units, display rows, predeclared summaries and optional ANM
   evidence. This is the only model payload.
3. Run record: public evidence, versions/digests, prompt, raw generation, parsed
   proposal or failure, cost/latency, release/check result and cache references.

Generate opaque IDs independently of source IDs. Randomize the A/B orientation
independently of the label using a recorded seed, and retain it across all four
packages. The evaluator alone maps predicted A/B directions back to reference
directions. A dataset split is fixed at source-family level before prompt tuning.

## Evidence construction

| Package | Names/units | Numeric display | ANM result |
| --- | --- | --- | --- |
| E1 | Sanitized | Absent | Absent |
| E2 | Anonymous A/B, no revealing units | Fixed rows + summary | Absent |
| E3 | Sanitized | Identical to E2 | Absent |
| E4 | Identical to E3 | Identical to E3 | Cached diagnostic + caveats |

Use one public question: “Which direction is more plausible, A → B or B → A?
You may abstain.” Provisional sample limits: 64 display rows and 256 ANM rows;
disclose actual sizes and validate these limits during the pilot. Select the
display rows as a deterministic subset of the method sample where feasible, with
the exact sampling policy/version recorded. Do not silently drop invalid rows.

Proposed summary, computed once and reused: displayed-row count and per-column
min, max, mean and population standard deviation. Omit summaries of undisplayed
rows initially. State the summary basis explicitly. More statistics are a pilot
decision, not a hidden difference between conditions.

Use separate `display_sample_digest`, `method_sample_digest`, `method_config_digest`
and `evidence_digest`. The two samples may differ: their hashes need not be equal.
The evidence digest binds the full public package; E2 and E3 therefore have
different evidence digests despite identical numeric display digests. Keep raw
row indices and original column names out of public provenance.

## Conditions and execution

- S0: one structured direction-prediction call.
- S1: one call using exactly the same evidence and output schema, adding explicit
  caution about uncertainty, evidence support and causal claims.
- S2: deterministic checking of a persisted S1 record. No generation, repair,
  reprompt or automatic regeneration. Retain both original and release outcomes.

Both S0 and S1 allow abstention and use a common scientific scope statement.
S1 adds caution; it must not receive extra numeric evidence or a larger budget.
Record condition order and avoid systematic run-order effects during live pilots.

For N pairs and four packages: 8N primary model calls, before explicit retries.
Twenty pairs imply 160 calls. S2 adds zero model calls. The existing Track A
multi-stage pipeline is a separate budget and condition family.

Cache by evidence digest, prompt version and full messages, output-schema version,
model identity/configuration, and replicate identifier. Persist raw text before
parsing and record errors without discarding cases. Never reuse an old cache
entry after evidence, prompts, model settings or schema change. Unknown usage and
cost remain null; a mock's token usage is not measured model cost.

No implicit retries initially. An explicit retry must be another logged attempt
with a parent attempt ID and bounded policy. Resume skips completed attempts,
including failures, unless an explicit retry is requested.

## Proposed module/API boundaries

These names are suggestions for review, not claims about existing code:

| Proposed location | Owner / responsibility |
| --- | --- |
| `discovery/schemas.py` | Vaishak + Kris: public evidence, method result, prediction and process-check types |
| `discovery/evidence.py` | Kris: package construction, summaries and public evidence hashes |
| `discovery/loader.py` | Faizah: source audit and runtime/evaluator separation |
| `discovery/anm.py` | Anish: label-free diagnostic |
| `llm/predictor.py` | Vaishak: `predict(evidence, condition) -> prediction attempt` |
| `verifier/checks.py` | Vaishak: `check_prediction(evidence, saved_prediction) -> process check` |
| `evaluation/runner.py` | Kris: conditions, persistence, caching and release orchestration |
| `evaluation/scoring.py` | Faizah: post-run label join, weighted metrics and source-group intervals |

Prefer injecting predictor and checker interfaces so mocks and real adapters run
through the same runner. Reuse `JSONModel`/`Generation` without changing Track A.
The runner owns durable logging; predictor results must expose prompts, schema,
raw generations, parsed proposal and failure stage rather than only an arrow.

## Proposal/checker contract questions

Proposed output: response action, nullable predicted direction (`A_to_B` or
`B_to_A`), cited evidence identifiers, nullable method-direction attribution,
structured claim scope and a short explanation. Answer requires a direction;
abstention requires null. Do not require uncalibrated numeric confidence.

The checker can deterministically validate bindings, cited evidence availability,
method decision consistency and explicit claim-scope flags. It cannot establish
that every free-text sentence is supported without an additional semantic
mechanism. Freeze a bounded claim taxonomy and separately audit explanations;
do not describe a metadata-only check as comprehensive overclaim detection.
Qualified disagreement with ANM is allowed. Agreement is not a release criterion.

Use process statuses such as `passed`, `rejected`, `error`, plus separate model
abstention and released-direction fields. A passed check is not a verified arrow.
Define handling of ANM errors/unconfigured threshold explicitly: expose the
failure/limitation in E4, prohibit a claimed method direction, and retain the case
for the predeclared analysis rather than silently removing it.

## Delivery sequence and acceptance gates

1. Audit baseline: run repository checks unchanged; record exact revision and
   environment. Inspect current code rather than assuming the roadmap is merged.
2. Interface proposal: answer the three collaboration questions with this
   bounded design; obtain Vaishak/Faizah review of shared boundary choices.
3. Mock slice: three synthetic runtime cases, each with E1–E4; S0/S1 scripted
   outputs, persisted S1, deterministic mock S2, and one reproduction command.
   Mock output is integration evidence, never research performance.
4. Verify behavior: no evaluator fields in prompts/tool inputs; E2/E3 numeric
   equality; stable orientation and seeds; cache invalidation; zero model calls
   during S2; failures and original proposals survive serialization.
5. Real integration: adapt Faizah's loader, Anish's diagnostic and Vaishak's
   predictor/checker behind the same interfaces. Recheck Track A regression suite.
6. Pilot: only audited eligible pilot source groups; inspect prompts and costs;
   validate method controls and matched comparisons; include simple gate and
   method-only baselines.
7. Freeze then evaluate: versions, sampling, thresholds, prompts, eligibility,
   schemas and metrics fixed before held-out runs. Score after label join.

Tests should include ANM ambiguity, tool failure, stale digest, false method
attribution, qualified disagreement, model abstention, malformed JSON and model
outage. Injected checker violations are scored separately from natural errors.

## Evaluation interpretation

Report weighted correct-answer yield, wrong-answer yield, coverage, selective
accuracy, process errors and failures/cost together. Bootstrap paired contrasts
by source family, not independently by pair or package. Faizah owns scoring.

For a filtering-only S2, correct-answer yield cannot exceed the same cached S1's
yield, and coverage cannot increase. The useful tradeoff is wrong answers removed
versus correct answers suppressed, including comparison with a simple gate.
Selective accuracy may rise simply through abstention. No released predictions
means selective accuracy is undefined, not zero or perfect.

## Decisions to settle before live pilot

- Vaishak's actual Track B schema/API, structured claim taxonomy and checker scope.
- Faizah's loader contract, eligibility/source groups and sanitized names/units.
- Anish's exact digest convention, summary ownership and method/config version.
- Model identity and availability, immutable model version/digest where possible,
  live budget and pilot ordering.
- Current team progress and authoritative Canvas deadlines: early roadmap dates
  are historical targets, not evidence that work has been completed.

## Base version v1: implementation specification

This section supersedes tentative choices above where more specific. Kris owns
this workstream's design and delivery. Teammates need to confirm boundary formats,
not approve every internal implementation decision. v1 is the complete baseline;
optional extensions follow only after its acceptance gates pass.

### Scope and explicit completion boundary

**Owned:** deterministic E1–E4 assembly; display summaries; package citation IDs;
S0/S1 prompt templates; experiment configuration; injected predictor/checker
adapters; sequential runner; cache/resume; append-only attempt/release logs;
model-independent simple gate; method-only baseline projection; label-free export
for Faizah; reproducibility manifest; contract/integration tests and independent
audit command. Track A runner routing may invoke its existing public pipeline but
is not part of the Track B factorial experiment.

**External implementations:** source ingestion, eligibility, source-family splits,
name sanitization and gold mapping (Faizah); regression/HSIC and ANM threshold
selection (Anish); production predictor/parser adaptation and process checker
(Vaishak); exact graph/witness work (Arunima/Anish); weighted scoring and confidence
intervals (Faizah). We implement mocks/adapters, not competing versions of these
components. Kris owns prompt text supplied to the predictor; the adapter must not
silently add a different caution policy or invoke a multi-call agent.

**v1 exclusions:** training, multiple discovery algorithms, multi-agent inference,
parallel execution, automatic repair/retries, dashboards, calibrated confidence,
comprehensive semantic explanation verification, and broad model sweeps. An
offline scripted run establishes software integration, never causal accuracy.

v1 delivery requires an offline reproduction command, audited artifact bundle,
passing existing repository checks, and passing consumer integration against actual
teammate adapters. A live smoke run is a separate readiness gate; held-out research
completion additionally requires frozen protocol, real runs and Faizah's scoring.

### Research contrasts and interpretation

| Question | Frozen comparison | What must be checked | Scope of inference |
| --- | --- | --- | --- |
| Names | E3 minus E2, within S0 and within S1 separately | Same numeric bytes, mapping, schema and model config | Incremental names/units/context; E1 describes context-only behavior |
| Method evidence | E4 minus E3, within condition | Same displayed data/context; one frozen method card added | Added ANM evidence bundle, including its larger sample and caveats |
| Caution | S1 minus S0, within package | Only the specified system instruction differs | Effect of that prompt intervention, not generalized reasoning ability |
| Checking | S2 minus its exact parent S1, primary E4 | Same proposals and denominator; no generation | Release tradeoff, process violations caught and useful answers suppressed |

E2 is anonymized, not guaranteed free of semantics: numeric scale and distribution
can reveal a variable. State this limitation. E4 with 256 method rows versus 64
displayed rows is not a pure algorithm-at-equal-information ablation; describe it
as additional method evidence. Equal-sample E4 is an optional later robustness run.
All directional outcomes are agreement with imperfect reference labels.

S2 filtering cannot improve correct-answer yield over the same S1 outputs.
Report correct predictions retained/suppressed and wrong predictions removed,
with coverage and selective accuracy, rather than promise increased useful yield.
Process validity and predictive correctness are separate axes. Mechanism tests
use injected corruptions reported separately from natural error prevalence.

### Architecture and information boundaries

| Record | Required content | Consumer |
| --- | --- | --- |
| RuntimePair | Opaque ID, finite two-column rows in runtime order, approved names/units, opaque snapshot/version reference | Evidence builder and numeric adapter |
| SelectionRecord | Sampling algorithm/version/seed, chosen indices, A/B permutation, source snapshot hash | Private reproducibility sidecar; never prompt |
| EvidencePackage | Version, case ID, E1–E4, question, allowed evidence items and sample counts | Predictor and checker |
| ExperimentSpec | Model identity/config, prompt/schema versions, package/condition list, seeds, sample limits, code revision | Runner/cache/auditor |
| PredictionAttempt | Invocation ID, cache key, public evidence, rendered messages/schema, raw generation or transport failure, parsed result/error, usage/time | Store, checker, post-run export |
| ReleaseRecord | Parent attempt ID/hash, checker name/version, process status/reasons, released nullable direction | Scorer and auditor |
| EvaluatorRecord | Gold direction, weight, source group, split, original source mapping | Faizah only; joined after runs |

The orchestrator can read scheduling and reproducibility metadata, but model
messages are constructed by explicit allowlist. The ANM request contains numeric
rows and configuration only, with public A/B coordinates. Original source names
and column indices stay in the private sidecar; no gold-oriented column sorting.
Private source mappings are not needed by the checker: it checks hashes and A/B
coordinates. Avoid including E4-only method counts/configuration in E1–E3 prompts.

### Evidence details we own

For v1 select up to 256 valid paired rows without replacement, then up to 64
of those for display, with separately recorded seeded generators. Eligibility
comes from the loader; builder rejects malformed/nonfinite inputs rather than
imputing, silently removing rows or pretending an error is an empty dataset.
Constant numeric columns are recorded as a diagnostic limitation, not repaired.
Preserve source order among selected rows. Use original finite float values for
serialization; do not introduce unrecorded standardization or unit conversion.
ANM's internal transforms are Anish's responsibility and must be recorded.

Summary statistics refer to exactly the serialized display values. Define mean
as sum/n and population standard deviation with denominator n. Display rounding,
if later introduced, must precede summaries and hashes or be explicitly represented
as a separate transform. v1 JSON uses canonical sorted keys, compact separators,
UTF-8, no NaN/Infinity, and a versioned finite-number representation with signed
zero normalized. Cross-adapter golden vectors verify serialization agreement.

Each public package has an evidence registry: `context:A`, `context:B`,
`rows:r0001` etc., `summary:A`, `summary:B`, and `method:anm:v1` only where present.
Row IDs are local display positions, never original dataset indices. Registry
membership is package-specific: E1 cannot cite rows and E2 cannot cite context.
Citation membership proves availability only; a separate value/claim check is
needed to establish faithful use. Full evidence and method digests remain in the
trusted request envelope; the runner supplies them, not model-authored claims.

Method sample hash binds the ordered numeric A/B values plus convention version.
Configuration hash binds method settings, preprocessing policy and threshold
version. The full package hash binds the exact visible payload, excluding its own
hash field. The display hash binds rows and order. Share one implementation or
verify golden vectors against Anish's hash convention through an adapter.

### Minimal prediction and invocation boundary

We define our adapter contract now. Adapt external names without changing meaning:

- `render(package, condition, spec)` returns exact messages and output schema.
- `predictor.generate(messages, schema)` returns raw Generation with observed
  model identity/usage when available; reuse JSONModel shape where possible.
- Strictly parse a separate direction proposal: action, nullable A/B direction,
  evidence reference IDs, optional method attribution, bounded claim scope and
  explanation. Keep schema identical across S0/S1 and packages.
- `checker.check(package, saved_attempt)` returns process result only, with no
  model handle. Runner derives S2 release and records the checker version.

Vaishak may expose a higher-level predictor. Its adapter must return exact rendered
messages/raw generations and satisfy the one-generation contract. Both prompts
use the same short task definition and allow abstention. The S1 caution paragraph
is a versioned additional instruction; it must not disclose new assumptions or
method data unavailable to S0. Prompt files and schemas are executable artifacts,
not prose descriptions. Do not freeze precise external schema names prematurely.

S0/S1 release a direction only when a structurally valid proposal answers. Model
abstention, parse failure, transport failure and checker suppression are distinct
stored outcomes. S2 never converts an abstention into an answer or changes an
arrow. An error cannot be mistaken for an ordinary model abstention.

### State, persistence and resume

Execution states: scheduled -> started (persisted before invocation) -> generated
(raw generation durably persisted) -> parsed or failed -> optional checked.
Interrupted starts become `interrupted_unknown`, never silently retried. A remote
call can complete before local persistence, so exactly-once remote billing cannot
be guaranteed; record that uncertainty and require an explicit new attempt.

Use sequential v1 execution, local append-only JSONL with flush/fsync and atomic
manifest/cache-index replacement. Detect and quarantine a partial final record on
recovery with an audit entry; never silently discard it. Duplicate key or conflicting
result detection fails closed. Cache reuse has provenance and is not counted as
a new model call. Cached historical tokens/cost are reported separately from new
execution usage. Store unavailable usage as null, never fabricated zero.

All cache keys include rendered messages/schema, public evidence, full model
configuration, resolved model identity if available and replicate ID. Run manifests
also retain source/prompt/code versions. If immutable model identity cannot be
established, cross-session reuse is disabled or explicitly marked unverified.
S2 cache identity additionally includes parent attempt hash and checker version.
Replay reads parent S1 records from disk with the model disconnected.

### Baselines and analysis export

Simple gate: release a valid S1 answer only when the package satisfies its public
availability contract (required context for E1; data for E2/E3; successful configured
method for E4). No gold, ANM agreement rule or explanation inspection. It uses the
same cached S1 parent so coverage reduction is directly comparable with S2.
Freeze this exact rule before pilot scoring; report rejection reasons.

Method-only: project Anish's configured diagnostic to A/B direction or abstention;
errors and unconfigured threshold remain explicit nonanswers. No model call.
Kris supplies execution/export; Anish owns method validity/threshold, Faizah owns
performance calculation.

Every scheduled eligible case has a terminal outcome for each planned condition.
Export case ID, package, condition, attempt/parent IDs, prediction/release, failure,
process reasons and versions. Faizah joins weights/groups/gold afterward. Manifest
stores expected case-condition keys so missing records cannot vanish from metrics.
Define paired E3/E4 reporting over all scheduled cases, including method failure;
any successful-method subgroup analysis is separately labeled and prespecified.

### Phases, deliverables and exit tests

| Phase | Deliverable | Exit evidence | External dependencies |
| --- | --- | --- | --- |
| 0: specification | This scope, frozen v1 choices, research matrix, question list | Every owned feature maps to acceptance test; unresolved boundaries listed | None; completed design is not tested software |
| 1: contracts/evidence | Typed records, package builder, registry, hash vectors, exact prompt files, sample fixtures | Label sentinels absent; malformed data rejected; E2/E3 and E3/E4 differential checks pass | Use synthetic RuntimePair/ANM fixtures |
| 2: runner/store | Injected adapters, sequential execution, raw persistence, cache/resume, replay, CLI | 3 cases x 4 packages x 2 prompts = 24 calls; S2 and resume add 0; failures survive | Scripted predictor/checker |
| 3: independent audit | Separate artifact auditor, golden expectations and corruption tests | Auditor rejects altered rows/digests, missing/duplicate trials, extra S2 calls and changed releases; clean run passes | No live model required |
| 4: integration | Real loader/ANM/predictor/checker adapters, export consumer fixture | Partner outputs pass our boundary fixtures; Faizah consumes export; Track A suite passes | Actual teammate handoffs |
| 5: pilot/freeze | Live smoke then 15–20 eligible pilot pairs if feasible; frozen spec | Prompt inspection, budget/context fit, complete run matrix, failure accounting, audit bundle, preliminary scoring | Audited source groups, model available, checker/method validated |
| 6: held-out handoff | Frozen execution, auditable export and reproduction note | No test tuning; counts reconcile with scorer; limitations recorded | Team protocol and Faizah scoring |

Suggested implementation PRs: contracts/evidence; runner/cache; audit/baselines;
external integration. Keep existing Track A source and exported schemas stable.
Shared-interface changes get affected-owner review; independent mocked progress
continues without waiting for their full implementation.

### Independent audit/testing procedure

Independence means a separate verification path, not calling the same builder and
asserting its output equals itself. No new agent is required. Auditor reads saved
artifacts; it does not import package-building/scheduling/release-policy helpers.
It may use schema validators but computes expectations from the spec and small
hand-calculated fixtures. A human/teammate reviews the audit report and samples.

| Invariant | Independent check | Fault that must make it fail |
| --- | --- | --- |
| No evaluator leakage | Trace all model messages/ANM requests; use gold/source-description sentinel fixtures and explicit field allowlist | Inject evaluator field or secret into exported context |
| Matched evidence | Compare serialized numeric values/row IDs and summaries across E2/E3/E4 | Change one row, statistic or orientation in E3 |
| Package visibility | Inspect registry and payload against E1–E4 matrix | Attach rows to E1, names to E2 or diagnostic to E3 |
| Numeric correctness | Hand fixture A=[1,3], B=[2,6]: means 2/4, population std 1/2, extrema/count known | Use sample std or summarize method-only rows |
| Mapping correctness | Swap columns on fixture and reverse expected evaluator direction; check matching label/context orientation | Double swap, reference-based ordering or stale method orientation |
| Binding | Independently hash canonical saved values; compare supplied known hash vectors | Alter rows/config/parent after generation |
| Prompt isolation | Compare S0/S1 rendered messages; only caution instruction differs | Additional evidence or unequal settings in S1 |
| Calls and cache | Counting fake transport + persisted invocation ledger; replay with transport that raises on any call | Model call during S2 or resume; stale cache after prompt change |
| Release integrity | Released S2 direction equals parent S1 direction or null; reasons/version present | Change direction or release a malformed proposal |
| Failures and coverage | Manifest expected keys vs terminal records, duplicates and explicit failed outcomes | Omit timeout or write duplicate condition |
| Recovery | Interrupt before/after generation, truncate final JSONL record, restart | Automatic rerun of unknown call or silent record loss |
| Consumer compatibility | Faizah's hand-scored toy table and adapter fixture serialization | Wrong direction enum, missing failure row, lost parent ID |

The auditor's own validation includes deliberately corrupted artifacts. Tests must
show each detector fails for its target fault, not only passes the clean bundle.
Checker mechanism audit uses independent expected decisions: missing method,
stale hash, false ANM attribution, unavailable row citation; plus qualified ANM
disagreement and valid abstention controls that must not be wrongly suppressed.
A mock checker validates orchestration only; production checker correctness is
not established until these tests run against Vaishak's actual implementation.

Free-text audit: inspect all pilot explanations initially, using a rubric for
unavailable evidence, false numeric/method attribution and causal-certainty claims;
record audit labels separately from model-visible data. Freeze rubric/examples
before held-out analysis and double-review disagreements if team capacity permits.
This supports bounded process-error reporting without claiming complete semantic
verification. No gold direction enters the runtime checker.

Run existing repository checks after meaningful implementation changes. Deliver
an audit report with code/spec versions, test commands, fixture expectations,
passed/failed checks, unresolved limitations and artifact hashes. A passing check
suite alone is not proof of research validity; phase 5 includes design review.

### What qualifies our collaboration answers as defined and verified?

After phase 0, answers can accurately state our chosen planned behavior and boundary
requests. After phases 1–3, concrete payloads, prompt snapshots, replay logs and
independent audit demonstrate that behavior. After phase 4, we can call interfaces
integration-tested. After phases 5–6, experimental claims require actual data,
scoring and uncertainty analysis. Never label a design proposal as empirically
validated. We do not need to finish live experiments before sharing useful
implementation commitments.

### Optional work only after v1 acceptance

Priority order: equal-sample ANM robustness; A/B-swap repeated runs to assess order
sensitivity; additional fixed replicates to estimate model variability; broader
summary sensitivity; parallel execution if runtime demands it. Each gets a new
version/analysis label. Do not alter a frozen held-out protocol in place or let
optional features delay the reproducible baseline.


## Phase 1 completion record

Local implementation now exists in `src/causalbridge/discovery/`: schemas,
selection/evidence construction, exact prompts and a reproducible contract example.
23 new test cases and all 67 existing tests pass; lint/format, original demo and
build pass. See `docs/knowledge/README.md` for commands and status. This completes
the local Phase 1 gate using synthetic fixtures. External adapter agreement,
production process checking and independent artifact audit are later gates.

Phase 1 clarifications: RuntimePair accepts original-column-order label-free
inputs and Kris assigns A/B orientation once; private selection records retain
the mapping. Evidence envelopes hold trusted hashes; only the payload is prompted.
Compact ANM cards are supplied by an adapter (fixture cards here), not computed
by our package builder. Proposal fields are structurally validated; evidence-use
and overclaim adjudication belong to the production checker and audit.
