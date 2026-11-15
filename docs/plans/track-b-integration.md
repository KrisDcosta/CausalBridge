# Track B integration handoff plan

Preserve the completed implementation and its release policy. Base: merged PR #1,
7a47465. No ANM, ingestion, experiment runner or scorer implementation.

1. Audit and commit Phase 1/2 on `codex/track-b-integration`. Exact source/test/
   fixture/doc allowlist only; include the three referenced planning sources.
   Exclude root proposal PDFs, generated output and ignored caches.
   Proof: `bash scripts/check.sh` (241-test baseline) and staged-content review.
2. Add `docs/track_b_integration_contract.md` describing implemented schemas,
   interfaces, all 32 codes, independent original-request provenance and owner
   handoffs. Add `examples/track_b_integration.py`, reusing existing fixtures,
   and `tests/test_track_b_integration.py`. Dependencies: preserved Phase 1/2.
   Proof: `uv run pytest tests/test_track_b_integration.py -q` and
   `uv run python examples/track_b_integration.py`.
3. Independent adversarial integration review, defect regressions if needed,
   full `bash scripts/check.sh`, explicit staged-file and secret/artifact review.
   Commit handoff/smoke additions locally. Do not push or merge.

## Pause checkpoint (resolved)

The following records the earlier pause state, superseded by completion below.

Branch: `codex/track-b-integration`.
Preserved Phase 1/2 commit: `6e7232e` (20 files; 241-test full validation passed).
Integration additions remain uncommitted: contract, executable example, this plan,
15 smoke tests (passing). Independent reviewer reported 256 tests passed before
the five new reproducing regressions below. No push or merge occurred.

Independent review found a pre-existing checker failure-path defect:
`finish()` in verifier/checks.py uses invalid evidence.case_id to construct
PredictionCheck. model_copy(case_id=None/42/[]/{}) crashes instead of returning
invalid_evidence. Empty string also lacks a usable diagnostic identity.
Five tests added to tests/test_prediction_process_injections.py reproduce this;
they currently FAIL intentionally. The fix is NOT implemented yet.

Resume steps:
1. Make finish() use the original nonempty string case ID if valid, otherwise
   the explicit diagnostic marker `<invalid_case_id>`. Preserve candidate package
   and proposal digests and existing invalid_evidence/fail/nonrelease semantics.
2. Run regressions; document marker as diagnostic only, linked through saved
   candidate digests/run IDs. Do not infer a genuine case ID or change policy.
3. Finish contract validation/review record and plan completion. Run full
   `bash scripts/check.sh` (expected 261 tests after 15 smoke + 5 regressions).
4. Review staged contents/secrets/artifacts; commit integration additions and
   minimal defect fix locally. Report exact files/branch/commit and handoffs.
5. Do not push or merge without explicit user approval.

Unrelated root proposal PDFs remain untracked. Build outputs/caches/logs ignored.
Reviewer: independent read-only agent Dirac, completed; no further findings or
unresolved agent work. No need to repeat the full audit or rebuild Phase 1/2.

## Completion

Resumed at user request. The 5 reproducing regressions pass after a minimal
diagnostic case-ID fix in verifier/checks.py; policy and interfaces unchanged.
Full `bash scripts/check.sh`: 261 tests passed without warnings, lint/format
passed, Track A demo passed, wheel/sdist built. Standalone smoke: 11 records;
15 integration tests passed. Track A, predictor and Track B schemas unchanged.
Independent review completed; its sole confirmed defect fixed and tested.
Exact file manifest, owner handoffs, blockers and smallest live test are in
`docs/track_b_integration_contract.md`. Explicit staged-content/secret/artifact
review precedes the final local commit. No push or merge is authorized.
