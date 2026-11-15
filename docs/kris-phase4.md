# Phase 4: native component integration and remaining handoffs

Status: **available-component integration implemented and tested locally**.
The Phase 4 exit gate remains open for Faizah's real-data loader, evaluator mapping
and scorer-consumer acceptance. No live LLM or real-data benchmark has run.

## Newly merged work

Remote main `b1718e7` (PR #5) is merged locally at `d990af8`. Anish now supplies:
`discovery/anm_requests.py` original-request storage, `discovery/anm.py` actual
RBF-KRR/HSIC, `tools/inference.py`/`engine.py` numeric engine, and independent
small-pilot numerical confirmation tests. The previous “ANM unavailable” status
is superseded. Original Anish request/result/config/provenance records remain
his native formats, not fabricated receipts projected from a returned result.

## Architecture and compatibility decision

Kris's original Phase 1/2 proposal schema has evidence IDs, explanation and claim
scope. Vaishak's implemented schema has bound case/package identity and typed
method/row/summary claims. They are not losslessly interchangeable. The native
integration therefore preserves DirectionEvidence, DirectionPrediction,
PredictionExecution, VerificationContext and PredictionCheck throughout. It does
not wrap a converted reply and pretend it was the raw model output.

- `build_native_packages(selected, directory, config)` reuses our seeded selection
  and population-summary policy, then consumes the actual ANM producer. It saves
  the method request before computation, validates an existing complete attempt
  before reuse, and never silently retries interrupted method execution.
- `NativePackage` stores public evidence plus private selected rows/index mapping,
  original ANMRequestBinding and its artifact directory. Only DirectionEvidence
  enters model prompts; no private mapping, original request or source index does.
- `IntegratedRunner.run(packages, model)` calls Vaishak's real `predict_direction`
  with our frozen native S0/S1 instructions. A thin durable transport captures
  the actual request and persists Generation **before** his parser runs.
- `replay_s2(manifest_id)` loads saved evidence, S1 proposal and original receipt;
  it calls the actual `check_prediction`. It has no model or ANM execution call.
  Missing/failed proposals get operational skip records. Releases preserve the
  exact saved arrow; checks/reasons/findings and S1 run/attempt links are retained.
- A pure `direction_messages` helper was extracted from predictor.py so cache
  identity can bind the exact planned request. Existing predictor signatures,
  message text, parsing, bindings and release policy are unchanged.

The native protocol is versioned `integrated-track-b-v1`. Its output schema and
common formatting instructions differ from the original scripted Phase 1 examples.
Both conditions receive identical evidence/schema/configuration; S1 adds only the
frozen caution instruction. No earlier fixture/live results are pooled across
these protocol versions. We have generated no live experimental results yet.

Native canonical digests are recomputed from their actual native payloads using
`sha256:`-prefixed, ASCII JSON. We never prefix a hash computed under our older
normalized-zero convention. The common storage utility now accepts a serializer;
its legacy default is unchanged, while native storage preserves signed zero.
A regression exercises -0.0 through actual ANM, native prediction persistence and
production checking.

## Run locally

```bash
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run --extra anm python -m causalbridge.evaluation.integration_demo --output runs/kris-phase4-final
# Repeat: zero new model calls and no re-executed ANM attempts.
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run --extra anm python -m causalbridge.evaluation.audit_native --input runs/kris-phase4-final/experiment --output docs/knowledge/phase4-audit.json
```

This is **real ANM computation + actual predictor/checker code + synthetic data
and scripted model replies**. It is not LLM inference or a real-world benchmark.
Three cases exercise configured diagnostic, constant-column error and unconfigured
threshold. Smoke threshold 0.001 is explicitly tagged uncalibrated/integration-only;
it is not a scientific threshold choice or a tuned result.

Recorded outcome: 24 initial scripted generations; 12 saved-S1 checks; 0 new calls
on resume. 51 label-free analysis rows are exported. Native handshake audit passes
with zero findings. It separately verifies public payload/receipt identities,
saved actual ANM files, raw predictions, S2 parent/release identities, matching
conditions and trial/call accounting. It does not call the runner or checker.
The Phase 3 legacy auditor remains in place for the old protocol; it must not be
used to falsely certify a native-format bundle it doesn't understand.

## Baselines and evaluator handoff

`evaluation/export.py` supplies `analysis_rows(run, releases)`:

| Condition | Definition |
| --- | --- |
| S0/S1 | Valid bound native directional prediction or explicit abstention/failure |
| S2 | Actual check result, reason codes and release from the exact saved S1 |
| SIMPLE_GATE | Same S1; require package validity and, for E4, successful configured ANM; never require ANM agreement |
| ANM_ONLY | E4 method direction or explicit method abstention/error, without model inference |

Four package rows each for S0, S1, S2 and SIMPLE_GATE, plus one ANM_ONLY row per
case = 17 rows/case. All prediction failures remain in their scheduled rows. The
export includes opaque case and A/B mapping identity, parent/run/attempt IDs,
versions, direction, failure stage, process reasons and token usage. S2/baselines
make no extra model calls. Invocation records distinguish newly issued versus
historical cached usage; unknown values stay null and no monetary cost is invented.

`evaluator_mapping(packages)` is a separate private post-run handoff: case ID,
opaque A/B mapping ID, original column order, mapping seed and source digest.
No reference direction is read or attached by runtime code. This mapping enables
Faizah to orient her reference labels correctly instead of assuming original
column 1 remains runtime A. Mapping fields never enter predictor messages.

Faizah must confirm the export consumer on a small hand-scored fixture before we
claim scorer integration. No weighted scoring/bootstrap implementation is duplicated
here. No source-family split, eligibility or name sanitization is inferred from
synthetic integration success.

## Test evidence

18 new cases exercise actual native components, receipts, all three predictor
failure stages, strict sample/config reuse, ANM failure/unconfigured states,
qualified disagreement, false method citation rejection, interruption/recovery,
cache/config changes, signed zero, baseline failure accounting, private mapping
export and native-audit rejection of a substituted original receipt.

Full `bash scripts/check.sh` with the host environment overrides passes:
495 tests, lint/format, both reference and production-engine Track A demos,
Anish's real synthetic ANM handshake and wheel/sdist builds. Legacy Phase 1–3
checks remain passing. This establishes software integration on synthetic data,
not statistical validity or model performance.

## Remaining Phase 4 / before Phase 5

1. Faizah: actual loader, eligibility/snapshot/source-group manifest, approved names
   and units, original reference mapping and scorer-consumer fixture. Her shared
   questions remain unanswered at the latest read; nothing is guessed here.
2. Use a real eligible pair through the same selected-data adapter, then validate
   the post-run label join and complete denominator accounting.
3. Choose and pin the live model/settings and an approved pilot budget. Mutable
   model tags use session-scoped cache by default; only a pinned artifact should
   use verified cross-session cache identity.
4. Select/freeze ANM threshold on development data, freeze the native prompt/schema
   and audit policy, then run the pilot. The synthetic smoke threshold is not reused
   as an evidence-backed choice.

These external handoffs keep the overall Phase 4 gate open. Our available-component
integration, baseline projection and provisional export are implemented locally.


## PR review follow-up

Confirmed and fixed the `e1c68b1` audit gap: failed-parent and checker-error S2
records must carry `released_direction=null`. The exporter now refuses contradictory
releases too. Four new regression controls rehash the journal/update the export,
so rejection depends on semantics rather than stale hashes. Clean records still
pass. Current full validation is 499 tests plus all repository checks. See the
knowledge bank for reproduction and the refreshed native audit record.
