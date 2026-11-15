# Kris: defined v1 collaboration answers

Status: Phases 1–2 locally implemented and tested, updated 14 November 2026.
Mock runner/storage/replay validation passes. Actual production adapters, independent
artifact audit and live research validation remain pending. See `kris-phase2.md`.
See `kris-track-b-plan.md`, section “Base version v1”, for scope and acceptance gates.

## What will the E1–E4 evidence packages contain?

I will build four matched packages per case with one opaque ID, a fixed direction
question and one seeded A/B orientation independent of the reference label:

| Package | Public evidence |
| --- | --- |
| E1 | Sanitized variable names and units only |
| E2 | Anonymous A/B display rows and summaries; no names or revealing units |
| E3 | Exactly E2's numbers plus E1's names and units |
| E4 | Exactly E3 plus a cached ANM card with scores, decision/status, sample size and limitations |

Base sampling selects up to 256 paired rows and up to 64 display rows from them,
without replacement, with recorded seeds and no silent cleaning. Summaries are n,
min, max, mean and population standard deviation of the displayed values only.
Pilot validation can change these defaults before protocol freeze. ANM internally
owns regression preprocessing and its train/evaluation split.

Each package exposes only its available evidence IDs: context:A/context:B,
rows:r0001 etc., summary:A/summary:B and method:anm:v1. Row IDs are local display
positions, never original dataset indices. The trusted envelope retains separate
full-evidence, display-sample, method-sample and method-configuration digests.
No gold labels, original pair IDs/descriptions, weights or source mappings enter
model messages or numeric diagnostic inputs.

## How are you planning to structure the S0/S1 prompts and cached outputs?

I own the exact versioned S0/S1 messages. Both ask the same direction question,
allow abstention, use identical evidence and output schema, and share model settings
and generation budgets. S1 adds only an explicit caution instruction about uncertainty
and evidence support. Each condition makes one generation call.

I will retain rendered messages/schema, public evidence, raw generation before
parsing, parsed proposal or failure, versions/digests, model identity/configuration,
usage/latency and attempt IDs. Unknown usage remains null. Cache identity includes
the exact messages, evidence, schema, model configuration/identity and replicate.
Failures are preserved; retries require a new explicit logged attempt.

S2 reads the exact saved S1 attempt. It cannot call a model, repair, regenerate,
change the arrow or release an answer from a parent abstention. Both the parent
proposal and separate release record survive. Model abstention, parse/transport
failure and checker suppression remain distinct outcomes for scoring.

## How will the runner call my predictor and verifier?

I will provide injectable adapters around your predictor and checker. The runner
renders messages and supplies the output schema; the predictor returns raw
Generation plus any parsing metadata. If your API is higher-level, the adapter
must expose the exact actual messages, raw reply, usage and failure stage and
preserve the one-call condition contract.

After the raw S1 attempt is durably saved, the runner supplies its immutable
proposal and evidence to your checker. The checker returns process status, stable
reason codes and any check details. The runner stores a separate parent-linked
release record. These are Track B interfaces, separate from Track A's known-DAG
CausalBridge.run and positive/negative/zero effect schema.

For a proposed common boundary, direction is A_to_B/B_to_A or null, paired with
answer/abstain. Evidence references, optional method attribution and bounded
claim-scope fields support deterministic checks; exact external field names can
be translated by the adapter. A check pass establishes process validity, not
causal truth. Qualified ANM disagreement is allowed. Comprehensive free-text
support remains a separate audit unless an explicit semantic checker exists.

## Verification and handoff

The evidence/runner now passes fixture tests independently of teammate adapters.
The Phase 3 independent auditor still needs to inspect artifacts and detect
injected row/hash changes, missing/duplicate trials, leakage, extra S2 calls and
invalid releases. Contract tests then run against your actual predictor/checker
and Faizah's export consumer. Live results are a later research gate.

Outstanding teammate questions are in the shared collaboration document under
“Stuff Kris needs”; they concern concrete handoffs and boundary conventions rather
than permission to design this workstream.


## Implemented Phase 2 interface

`evaluation.runner.ExperimentRunner.run(envelopes, model, replicate_id="0",
retry_id=None)` uses the exact `discovery.prompts.render` messages/schema with
one `model.generate` per new S0/S1 trial. It journals started/raw/finished records,
retains failures, and resumes without implicit retry. `replay_s2(manifest_id,
checker)` reloads saved S1 and calls `checker.check(envelope, saved_attempt,
receipt)` with no model argument. Cache keys cover evidence/messages/schema,
source fingerprint, model/config/identity and replicate/retry. Check results
cannot change a saved arrow or parent identity. See the saved demo and test
commands in `kris-phase2.md` for proof of 24 initial/0 resumed calls.

These types live in `discovery/contracts.py` to avoid overwriting Vaishak's
merged `discovery/schemas.py`. His predictor/checker adapters require explicit
translation and original ANM provenance receipts; they are not implicitly
compatible. The compact model-visible MethodCard does not replace the detailed
ANM request or VerificationContext. The shared collaboration document has been
updated with concise answers stating this implemented/pending boundary.
