# Phase 3: independent saved-artifact audit

Scope: local offline evidence/runner/replay correctness. This is a separate
computational verification path written in this workstream, not a claim of an
independent human review or a production research evaluation.

## What is implemented

`evaluation/audit.py` reads artifacts without importing the evidence builder,
runner, journal implementation, parser, prompt renderer or production verifier.
It independently implements strict JSON reading, canonical hashing, statistic
calculation, sampling replay, trial reconciliation and minimum release checks.
It reuses contract classes only for record-shape validation.

`evaluation/audit_policy.py` is a frozen copy of the approved v1 question and
S0/S1 instructions. Protocol changes require a reviewed new policy; the auditor
does not silently accept whichever prompts the current renderer produces.

The auditor never modifies experiment inputs. Its CLI refuses to write the report
inside the audited directory. A report records pass/fail, findings/locations,
counts, scope flags, input-file hashes, policy identity, auditor source hash and
limitations. Unknown or malformed records fail the audit rather than being
silently ignored. A passing report is scoped to the artifacts and policy named.

## Reproduction

```bash
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run python -m causalbridge.evaluation.demo --output runs/kris-phase3-verified
# Repeat the same command: zero additional calls.
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run python -m causalbridge.evaluation.audit --input runs/kris-phase3-verified --output docs/knowledge/phase3-audit.json
PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache uv run pytest tests/test_artifact_audit.py -q
```

The demo contains three synthetic cases, four packages and two prompt conditions.
Its ANM and checker are explicitly scripted. The report is reproducible; runtime
artifacts are under ignored `runs/`. The checked report is saved in the knowledge
bank; it is not evidence of causal accuracy.

Default audit requires the full E1–E4 x S0/S1 matrix, S2 outcomes for every saved
S1, and original source/selection receipts. `--allow-partial-matrix`,
`--without-s2` and `--without-source` explicitly reduce scope, which is recorded
in the report. A reduced-scope pass is not the full Phase 3 gate.

## Checks

| Area | Independent verification |
| --- | --- |
| Journal | Strict JSON, sequence/hash chain, known event kinds, duplicate outcomes, start/generation order and terminal accounting |
| Selection | Private source digest, seeded orientation, method/display indices, original row order and source-to-A/B context/data mapping |
| Public evidence | Package schema/visibility, allowed public fields, evidence/display/method hashes and per-column population summaries |
| Matched design | Complete expected matrix, identical E2/E3/E4 numerics, identical named context, same model/config/schema for S0/S1 |
| Prompts | Exact frozen question/instructions, exact allowlisted user payload, no extra condition or evaluator fields |
| Predictions | Raw Generation preserved, strict parsed proposal equals raw reply, identity/status/failure consistency |
| S2 | Original S1 parent IDs/hashes, checker version, release/skip accounting, unchanged arrow, no S2 generation condition |
| Minimum process claims | A passing checker may not accept unavailable citation IDs, false method attribution or explicit causal-proof scope; qualified disagreement is permitted |
| Exports | Journal records agree with manifest schedule, original/latest exports and per-invocation files |
| Calls/usage | Invocation-linked new call keys reconcile with new/cached counts; unknown tokens remain unknown; historical usage is separate |

Minimum process checks do not replace Vaishak's detailed production checker.
False citations/claims on original S0/S1 may occur naturally; the audit flags a
checker incorrectly certifying them rather than treating all model mistakes as
corrupt execution. Injected violations are mechanism tests, not estimates of
natural error prevalence.

## Gaps found and closed during this phase

1. Phase 2 stored invocation counts but did not link each started call to its
   invocation. Runner v1.1 now saves `invocation_id` and `new_trial_keys`, enabling
   independent call/usage reconciliation. It still cannot prove a call made
   outside the instrumented transport never occurred.
2. Public packages alone cannot establish correct original column orientation or
   sampled rows. The demo now saves `provenance.json` BEFORE prediction, with
   label-free original RuntimePair data and private SelectionRecord values.
   These records are never sent to the model. Future real-data adapters must
   preserve the same information boundary; the auditor never invents missing
   receipts from returned method results.

Legacy Phase 2 bundles without these records are not automatically certified as
full v1.1 audits. Retain them as historical artifacts; generate a new frozen run
or audit them with explicitly reduced scope where appropriate. No prior live
model output needs to be discarded; none has been generated by this workstream.

## Adversarial acceptance evidence

31 test cases include clean/read-only/CLI checks and deliberately corrupted
summaries, rows, hashes, prompts, schemas, source mappings, method binding,
parent identity, arrow, trial accounting, exports, usage and event structure.
Several tests recompute the journal chain after alteration so success cannot
come only from detecting a broken outer hash. A separate import-boundary test
checks that the auditor does not import production verification helpers.

Checker controls include unavailable row, false method attribution and explicit
proof claims that a deliberately permissive mock checker passes incorrectly;
the auditor must reject these. Honest abstention and accurately attributed ANM
disagreement are negative controls that must pass. Timeouts and malformed model
replies remain valid recorded execution outcomes and are included in accounting.

Full combined suite: 334 tests pass, Ruff lint/format pass, unchanged eight-case
Track A demo passes, source distribution and wheel build. Fresh default-scope
report: 24 trials, 12 S2 records, 86 journal events, zero findings.

## Boundaries and next work

The source receipts are producer-supplied; verification is computational, not
cryptographic authentication of the original data. Approved names/free text can
still contain revealing information that needs human review. Hashes do not defend
against complete malicious rewriting. ANM math, real-data eligibility, source-group
splits, reference correctness, comprehensive explanation support and scientific
performance are not established by this audit.

Next is Phase 4: actual predictor/checker adapters, original ANM-request provenance,
real loader/scorer handoffs, and our pending baseline/export consumer integration.
These must preserve meaning across our contracts and Vaishak's schemas, not simply
rename fields or prefix unrelated hashes. No live-model or held-out claim is made.
