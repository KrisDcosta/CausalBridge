# Track B Phase 2 implementation plan

Specification: November 8 roadmap V2 and Section 7, Phase 1 handoff, team
interfaces. Goal: deterministic consistency checking over saved S1, never causal
truth, no model/method invocation or prediction replacement.

## 1. Typed provenance inputs and tests
Files: `src/causalbridge/verifier/bindings.py`, `tests/test_prediction_checks.py`.
Add ANMRequestBinding (saved before execution) and VerificationContext (runner's
trusted saved evidence/proposal receipt). No input may contain evaluator data.
The request independently supplies sample/config identity, mapping, counts,
seeds, threshold and versions. Missing trust inputs cause checker abstention.
Dependencies: inspected Phase 1; 164-test baseline.
Proof: `uv run pytest tests/test_prediction_checks.py -q`.

## 2. Deterministic checks
Files: `src/causalbridge/verifier/checks.py`, `tests/test_prediction_checks.py`,
`tests/test_prediction_process_injections.py`, `tests/test_direction.py`.
Reuse PredictionCheck and Phase 1 schemas. Revalidate saved models; verify exact
package/proposal binding, original request/result provenance, typed method,
row and summary claims. No probability claim vocabulary expansion; invalid
fields remain schema errors. Compare numeric citations exactly against saved
numbers; Phase 1's documented ANM arithmetic tolerance remains unchanged.
Policy: any contradiction fails; missing trust inputs abstain; otherwise pass,
releasing only if S1 itself answered. No minimum claim requirement.
Dependencies: typed inputs. Tests first, separate deliberate process injections.
Proof: `uv run pytest tests/test_prediction*.py tests/test_direction.py -q`.

## 3. Review, handoff, examples and full verification
Files: `docs/track_b_phase2.md`, `examples/track_b_phase2.jsonl`.
Document exact API, each reason code, required Anish records, storage trust
boundaries and impossible checks. Keep Phase 1 artifacts/predictor unchanged.
Perform a separate adversarial review without adding an agent or LLM verifier;
reproduce confirmed defects with failing regression tests before fixing them.
Proof: `bash scripts/check.sh` and schema/digest round-trip of saved examples.
No commits or pushes.

## Completion
Tasks 1–3 complete. Full check: 241 tests passed (77 new), lint/format passed,
Track A eight-case demo passed, wheel/sdist built. Separate adversarial review
confirmed order-dependent findings and silently dropped model_copy extras;
five reproducing tests failed before fixes and now pass. Existing source files
apart from verifier/checks.py and all exported schemas are unchanged. All four
saved Phase 2 examples reproduce exact outputs. See `docs/track_b_phase2.md`
for complete contracts, reason codes, trust boundaries and remaining assumptions.
