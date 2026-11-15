# Implementation inventory — 2026-11-14

## Anish's updated branch audit

Fresh clone: `CausalBridge-Anish`, base `48d6cda` (merged PR #4), feature branch
`codex/anish-anm-provenance`. All remote branch heads were fetched and compared.
`codex/benchmark-graph-witness` (PR #1), `codex/benchmark-small-pilot` (PR #2),
`codex/exact-known-witness-joint` (PR #3), and `codex/track-b-integration` (PR #4)
are represented in main. No other remote implementation branch was present.
The earlier `anish/causal-engine` work existed locally only; its numerical
functions/tests are carried forward without replacing merged structural helpers.

Authoritative interface: `docs/track_b_integration_contract.md`, ANMRequestBinding,
ANMResult/ANMProvenance, DirectionEvidence, VerificationContext and check_prediction.
These existing schemas, predictor, checker and graph/witness modules are unchanged.
New files supply the numerical producer and durable originals described in
`anm_producer.md`. Real-data loader/scorer and actual experiment runner are not
present on the inspected branches. Their absence does not block synthetic tests.

## Historical Vaishak inventory

Inspected local parent `042d558` and merged PR #1 (`7a47465`), then fast-forwarded
to that merge. PR #1 adds `benchmark/generator.py`, `benchmark/witness.py`, graph
query helpers, and tests. It preserves existing RuntimeCase/CPT v1.0 conventions.

Reusable interfaces:
- `schemas.py`: frozen, extra-forbid `Record`; Track A RuntimeCase, CPT, Query,
  Proposal, ToolRequest/Result and Verdict stay unchanged.
- `llm/client.py`: JSONModel.generate(messages, schema), Generation, ModelConfig,
  OllamaModel; bounded `/api/chat` structured generation, no retries/downloads.
- `llm/parser.py`: duplicate-key-rejecting, size-bounded parse_json and messages.
- `pipeline.py`: CausalBridge.run and RunTrace are Track A's parse/plan/execute/
  interpret path; useful trace conventions, unsuitable for single-call Track B.
- `verifier/contracts.py`: operation/precondition/effect checks stay Track A only.
- `tools/protocol.py`: existing ToolBackend stays unchanged; Track B consumes a
  cached ANMResult rather than routing through the graph operation enum.
- `tests/`: parser, schemas, transport, input errors, pipeline, verifier, numeric
  adapter, graph/generator and witness regressions.

Python >=3.12,<3.15; Pydantic 2, NetworkX 3, httpx; pytest/Ruff via uv.
Existing demo: `uv run causalbridge demo --output runs/demo.jsonl --overwrite`.
Existing full check: `bash scripts/check.sh`.

Baseline: direct pytest at the parent produced 65 passes and two PATH-related
CLI launch failures. With `.venv/bin` on PATH, merged PR #1 passes **102 tests**.
Serena symbol inspection was attempted but unavailable (no active language
server); inspected source directly. `gh` was unavailable; GitHub connector
supplied the merged PR metadata and complete diff.

Pre-existing untracked proposal PDFs and `docs/planning/` are user inputs.
No live model, external dataset or independent ANM implementation is assumed.
