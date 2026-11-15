# Kris Phase 2: durable execution and saved-S1 replay

Implemented locally on `codex/kris-track-b-plan`, after merging remote main
`48d6cda` (PRs #1–#4). Phase 1 contracts moved from `discovery/schemas.py` to
`discovery/contracts.py` to preserve Vaishak's public schemas unchanged.

## Reproduction

```bash
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run python -m causalbridge.evaluation.demo --output runs/kris-phase2
# Repeat: zero new transport calls, all 24 trials reused.
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run pytest tests/test_experiment_runner.py -q
```

Three synthetic cases, four packages, two prompts produce 24 scripted calls.
The 12 saved S1 outcomes produce parent-linked S2 records with zero additional
model calls. Demo ANM and checker behavior are fixtures, not computed statistical
results or production checker validation. Re-running the same source/spec uses
saved results; changed source fingerprints intentionally invalidate the cache.

## Public interfaces

`ExperimentRunner(root, model_identity=..., config=..., model_mode=...,
identity_verified=...)` in `evaluation/runner.py`:

- `run(envelopes, model, replicate_id="0", retry_id=None)` makes only scheduled
  S0/S1 calls using the Phase 1 exact messages/schema. It returns manifest ID,
  invocation ID, new-call count, cached/recovered count, distinct new/historical
  token totals, null monetary cost, and complete per-trial start/outcome records.
- `replay_s2(manifest_id, checker)` has NO model argument. It loads original
  evidence, attempts and binding receipts from the journal and invokes
  `checker.check(envelope, saved_attempt, receipt)`.
- Checker adapters return `ReleaseRecord` and expose a stable `version`.
  Release may preserve a saved direction or abstain. A changed direction,
  parent identity/digest or checker version is recorded as checker_error.

Original S0/S1 attempts, S2 releases and operational failures remain separate.
A failed S1 creates an explicit skipped S2 record, not a scientific abstention.
A passed process check on a model abstention still releases no direction.

## Stored artifacts

| Path | Content |
| --- | --- |
| events.jsonl | Append-only sequence/hash-linked started, generated, finished, released, recovery and invocation events |
| manifests/<id>.json | Expected trial keys and case/package/condition schedule |
| invocations/<id>.json | Immutable per-invocation export including new versus historical usage |
| exports/<manifest>.json | Latest complete trial export, preserving original attempt records |
| exports/<manifest>-s2.json | S2 operational/process outcomes with parent linkage |
| quarantine-*.bin | Preserved incomplete final journal bytes during crash recovery |

The journal is authoritative; indexes are rebuilt from it rather than trusted
from a disposable cache file. Writes flush/fsync; atomic JSON replacements fsync
file and parent directory. A process lock serializes each run/replay. Completed
malformed/hash-invalid records fail closed. A partial final line is preserved
before truncation and recovery is journaled. This is accidental-corruption/crash
handling, not protection against an actor able to rewrite the entire journal.

Started is persisted BEFORE invoking transport. Raw Generation is persisted BEFORE
parsing. On resume, a saved raw generation can be parsed without a new call.
A started invocation with no raw result becomes interrupted_unknown, without
automatic retry: remote execution/billing may have happened before the crash.
Exact-once remote billing is not promised. An explicit retry_id creates another
attempt and records its prior same-evidence/condition/replicate parent if present.
Same retry ID resumes the retry rather than issuing it repeatedly.

Cache keys include public evidence/envelope, full messages/schema, condition,
prompt/runner version, package source fingerprint, model config and identity,
replicate and explicit retry ID. Unverified model identity adds a session nonce,
disabling cross-session reuse. Set identity_verified only for a pinned model
artifact or deterministic fixture, not a mutable model name alone. Unknown token
usage is null; an empty set of newly issued calls has usage zero. Cached usage is
historical, not billed again. Transport failures preserve unknown usage.

## Merged work and adapter boundaries

Vaishak's `predict_direction(DirectionEvidence, PromptCondition, JSONModel)` and
`check_prediction(DirectionEvidence, DirectionPrediction, context=VerificationContext)`
are now real code, not just the older collaboration-document sketches. Their
schemas enforce typed claims and sha256:-prefixed digests. The shared document's
illustrative directional_scores output is not the current implemented schema.
Arunima's graph generator, witness validation, seven-question small pilot and
exact population-joint exports are merged. Independent Anish numeric confirmation
remains marked pending in the benchmark code.

Our runner consumes our Phase 1 contracts and exact prompt/schema; it does not
silently feed those records into Vaishak's differently shaped predictor/checker.
Our hashes use bare hex and normalized signed zero; his schema uses a distinct
canonical convention. Integration must compute each identity from its correct
payload; prefixing an arbitrary digest is not semantic conversion.

Phase 4 adapter must explicitly translate evidence/claims and preserve original
ANM provenance/request receipts saved BEFORE method execution. Do not derive
expected original ANM request values from the returned result. No real ANM
request is fabricated by Phase 2. The current replay receipt binds our original
public evidence and saved proposal; it is not a replacement for Vaishak's full
VerificationContext. Free-text explanations/claim_scope are not certified by his
bounded typed-claim checker. These boundaries may be reconciled by teammate
updates without changing our owned runner semantics.

## Acceptance checks

`tests/test_experiment_runner.py` covers the full 24-call matrix, cross-instance
disk resume, replay without generation, failed/abstaining parents, raw-text
retention, interruption before/after raw persistence, partial-tail quarantine,
completed corruption rejection, duplicate schedule/outcome checks, explicit retry
parents, model config mismatch, cache changes for evidence/prompt/schema/model/
config/replicate/checker, unverified identity sessions, usage accounting and a
checker trying to change the parent arrow.

Phase 3's separate independent artifact auditor is still pending. These tests
exercise persistence/replay correctness but do not establish causal accuracy,
production-checker integration or completeness of free-text overclaim detection.
