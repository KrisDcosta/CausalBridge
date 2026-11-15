# Team handoff checklist

## Anish: numerical engine and ANM request producer

Implemented locally from merged main `48d6cda` on `codex/anish-anm-provenance`
in the fresh `CausalBridge-Anish` clone. Anish has authorized committing and
pushing this feature branch; PR creation and merge remain separate steps.

- Track A `CausalEngineBackend` and reusable numerical functions preserve the
  reference backend and graph/witness code. Select with `--backend engine`.
- Independent rational tests confirm all merged small-pilot numeric labels and
  the same-P(X,Y), +0.30/-0.30 witness. Historical oracle tags are left intact.
- `save_anm_request` writes actual sample/config/split bindings and standalone
  `request.json` before any numerical execution. It never derives a request from
  returned provenance. `execute_anm_request` produces existing ANMResult objects.
- `load_anm_artifacts` resolves/checks reproducibility records and originals;
  the existing verifier consumes its saved request as context.method_request.
- `examples/anm_integration.py` demonstrates computed synthetic ANM, a scripted S1
  prediction and deterministic S2, with separately saved receipts and no new S2 calls.

See [producer/API guide](anm_producer.md), [verification](verification.md), and the
authoritative [Track B contract](track_b_integration_contract.md).

Outstanding: real eligible samples and source-group development evaluation,
matched E1-E4 packages, actual S0/S1 runner/cache, a frozen tau, and live model runs.
No numerical score here is a causal probability or proof. Do not reconstruct a
missing request from a result. Create a fresh directory for a retry.

## Vaishak: original orchestration handoff

## What you can demonstrate now

Run `uv run causalbridge demo --output runs/demo.jsonl`. Open the JSONL to inspect
the parsed query, selected tool, tool result and verdict for each fixture.

The paired toy cases keep the question and graph fixed. Complete CPTs support
+0.4; the graph-only case abstains. A deliberately wrong tool choice receives
`wrong_operation`. No-path zero and valid backdoor adjustment show that the verifier
can also accept useful answers.

## Roadmap deliverables

| Deliverable | Implementation |
| --- | --- |
| Structured query parser | `src/causalbridge/llm/parser.py`, `schemas.Query` |
| Tool planner | `src/causalbridge/llm/tool_planner.py` |
| Verification contracts | `src/causalbridge/verifier/contracts.py` |
| LLM orchestration | `src/causalbridge/pipeline.py`, `llm/client.py` |
| General operation requirements | `check_preconditions`, capability checks and conclusion checks |
| Accept computed effect; reject path-to-sign claim | `tests/test_contracts.py`, fixture demo |
| Work independently of Anish | `ToolBackend` protocol, reference adapter and hand-computed fixtures |
| Integration with Kris | Importable `CausalBridge.run`, versioned schemas and JSONL traces |

## Team integration steps

1. Review `schemas/` with Anish and Arunima. Confirm parent ordering, visibility,
   binary treatment convention, adjustment-set representation and assumption flags.
2. Anish's adapter is now selectable, with shared fixture parity and independent
   numerical controls. Retain the reference default until the team changes it.
3. Start the chosen model server. Run `examples/runtime_cases.jsonl` and inspect
   every parsed query, raw JSON reply, token count and failure stage.
4. Give Kris the pipeline entry point and `RunTrace` contract. Keep A–E data and
   generation budgets comparable. Agree how multi-call token budgets are matched.
5. Give Faizah example traces and reason-code meanings. Separate parse failures,
   wrong operations, inconsistent conclusions and model abstentions in analysis.
6. Use development cases to settle prompts and tolerances, then freeze code,
   prompt version, lockfile and model artifact before any held-out evaluation.

## Before calling the whole project complete

The numerical engine and independent pilot/witness checks are implemented. The
team still needs full benchmark validation, real-data/live-model runs, matched
baselines, group-level uncertainty estimates, scoring audits and the report.
