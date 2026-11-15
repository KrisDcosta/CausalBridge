# Track B Phase 1 implementation plan

Goal: add typed, single-call direction prediction while preserving Track A.
Specification: November 8 `docs/planning/Detailed_Implementation_Roadmap.pdf`,
with confirmed ANM conventions in `docs/planning/track_b_team_interfaces.md`.

## 1. Audit and baseline
Files: `docs/implementation_inventory.md`.
Inspect merged PR #1, schemas, parser, client, pipeline, verifier and tests.
Dependency: fast-forward local checkout to merged PR #1.
Proof: `PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest -q` (102 baseline tests).

## 2. Runtime contracts
Files: `src/causalbridge/discovery/__init__.py`, `discovery/schemas.py`,
`tests/test_direction.py`.
Reuse frozen, extra-forbid Record. Require finite numbers, E1–E4 restrictions,
consistent abstentions and ANM decisions. Separate display/method/package hashes.
ANM metadata uses typed provenance and an immutable reproducibility reference.
No labels, evaluator dictionaries, data loader, numerical method or runner.
Dependency: audit. Write negative tests first.
Proof: `uv run pytest tests/test_direction.py -q`.

## 3. Predictor and checker boundary
Files: `src/causalbridge/llm/predictor.py`, `verifier/checks.py`,
`tests/test_direction.py`.
`predict_direction(evidence, prompt_condition, model_client)` makes exactly one
JSONModel call using parse_json; preserves errors/raw generation and binding IDs.
PromptCondition carries runner-owned instructions, ID and version.
`check_prediction(evidence, saved_prediction)` returns a bound, non-releasing
Phase 1 placeholder. It performs no method/model calls or claim certification.
Dependency: contracts. Proof: `uv run pytest tests/test_direction.py -q`.

## 4. Offline handoff and verification
Files: `src/causalbridge/discovery/demo.py`, `docs/track_b_phase1.md`.
Demo emits E1–E4 inputs and traces, plus ANM ambiguity/unconfigured/error states.
Document provisional adapter fields, canonical JSON hashes and Phase 2 boundary.
Dependencies: contracts and predictor.
Proof: `uv run python -m causalbridge.discovery.demo`, `bash scripts/check.sh`.

## Review focus
- E2/E3 retain identical display identity; method sample may differ in size.
- Strict threshold boundary, missing threshold, execution errors and nonfinite input.
- No silent retries, cross-case/package outputs or fabricated calibrated scores.
- Arbitrary prose remains producer-sanitized; typed fields cannot detect mislabeled text.
- Preserve Track A files and schema exports byte-for-byte relative to PR #1.

## Completion
Tasks 1–4 completed. Full `bash scripts/check.sh`: 164 tests passed, lint and
format passed, Track A demo passed, wheel/sdist built. Offline demo: 7 records.
Independent review fixes have regression tests (RED → GREEN): score-based
threshold decisions and threshold-consistent mock provenance. The checker is
intentionally only the Phase 1 non-releasing interface. See `docs/track_b_phase1.md`
for exact API choices, reference resolution trust boundaries and remaining
teammate integration assumptions. No feature commit or push was requested.
