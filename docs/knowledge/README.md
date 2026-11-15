# CausalBridge knowledge bank

Start here when resuming work. This is an evidence-linked progress record, not a
claim that roadmap assignments have been completed. Update it alongside each
implementation milestone; fetch remote progress before marking teammates' work.

## Research and system context

Two tracks: Track A checks support for causal effects with a supplied DAG and exact
population evidence. Track B studies direction predictions from names, observations
and an optional ANM diagnostic. They share transport where useful, but have separate
schemas and correctness claims. A process-check pass does not verify a causal arrow.

Planning sources:
- [Shared planning folder](https://drive.google.com/drive/folders/1vx2vCUmMF_OcG24JXdpUQDmIBlh72ShG)
- [Collaboration questions](https://docs.google.com/document/d/1uTciRJR_YQT-UvEk8qh7B7cDMQttPMidOhNkzDm8Hq8/edit)
- [Kris implementation plan](../kris-track-b-plan.md), especially “Base version v1”.
- [Kris defined answers](../kris-collaboration-answers.md).

Status vocabulary: **planned** = specified only; **implemented** = code exists;
**tested** = named checks pass; **integrated** = actual consumer/producer exercised;
**evaluated** = real experiment with scored outcomes. Local unmerged work is marked
explicitly. Do not infer a teammate's status from assigned responsibility.

## Overall project inventory

Last remote snapshot observed: main `042d5589e2db25706337cc2112e0ce347c11b247`.

| Workstream | Owner | Evidence-backed status | Evidence / next dependency |
| --- | --- | --- | --- |
| Known-DAG parsing, pipeline, contracts | Vaishak | Tested on audited main | 67 original tests and eight-case demo; `docs/verification.md` is historical record |
| Exact reference graph/numeric backend | Existing development implementation; Anish owns production engine | Implemented and covered by original tests; production handoff not observed | `tools/reference.py`, `tools/graph.py`; development enumeration cap 12 nodes |
| Benchmark generation / exact witnesses | Arunima + Anish | Planned; no completed benchmark observed in audited main | `benchmark/` placeholder; roadmap witness is not a repo deliverable |
| Tübingen ingestion and split audit | Faizah | Planned / handoff pending | No real-data loader in audited main |
| ANM | Anish | Output design supplied; tested implementation not observed | Shared collaboration document; our cards are scripted fixtures |
| Track B predictor / process checker | Vaishak | Planned / handoff pending | No production Track B implementation in audited main |
| Evidence, prompts and execution | Kris | Phase 1 locally implemented and tested; execution pending | See phase tracker below |
| Scoring / intervals | Faizah | Planned / handoff pending | No scorer in audited main |
| Live pilot / held-out findings | Team | Not executed here | No research performance claims |

## Kris: plan versus actual work

| Phase | Current status | Actual deliverables | Remaining exit work |
| --- | --- | --- | --- |
| 0 Scope/design | Defined | Scope, architecture, research contrasts, phases and audit procedure; simplified shared questions | Maintain decisions as external handoffs arrive |
| 1 Contracts/evidence | Locally tested; integration pending | `discovery/schemas.py`, `evidence.py`, `prompts.py`, `example.py`; tests and contract example | External formats remain provisional; no teammate integration claim |
| 2 Runner/persistence | Planned | Attempt/release shapes only, no execution/store implementation | Durable logs, invocation ledger, resume/cache and model-free replay |
| 3 Independent artifact audit | Planned | Test matrix specified; no standalone auditor yet | Separate reader plus deliberate corruption tests |
| 4 Integration | Planned | No real external adapters yet | Loader, ANM, predictor/checker and scorer consumer |
| 5 Pilot/freeze | Planned | None | Live model, audited pilot groups, budget review and frozen protocol |
| 6 Held-out/handoff | Planned | None | Frozen runs, independent audit and scoring reconciliation |

## Phase 1 behavior and files

- [Contracts](../../src/causalbridge/discovery/schemas.py): no evaluator fields;
  strict finite rows; separate direction proposal; method consistency; attempt and
  process release shapes. These are our v1 boundary, adaptable to teammates.
- [Evidence](../../src/causalbridge/discovery/evidence.py): independent seeded
  orientation/method/display selection, local row IDs, population summaries,
  signed-zero-normalized canonical hashes, method binding, matched packages.
- [Prompts](../../src/causalbridge/discovery/prompts.py): exact common task plus
  S1-only caution paragraph, identical output schema, only public payload serialized.
- [Contract generator](../../src/causalbridge/discovery/example.py) and
  [generated example](../../examples/track_b_contract.json): four-row illustration,
  four packages, eight prompts, answer/abstention/failure and illustrative release.
  Not a valid ANM study: the method and release are explicitly scripted.
- [Tests](../../tests/test_discovery_phase1.py): hand calculations, sampling,
  mapping, visibility, invalid inputs, hashes, method errors and proposal records.

Reproduce from repo root:

```bash
uv sync --frozen --dev
uv run python -m causalbridge.discovery.example --output examples/track_b_contract.json
bash scripts/check.sh
```

This host intermittently loses editable-package import resolution across command
calls. Verified fallback sets `PYTHONPATH=src` and uses
`UV_CACHE_DIR=/tmp/causalbridge-uv-cache` for both commands. No production source
change was made for that environment issue.

## Decisions and limitations

| Decision | Reason / consequence |
| --- | --- |
| Separate Track B package | Track A direction is effect sign; Track B direction is A/B orientation |
| One seeded orientation across packages | Avoid introducing a label-oriented order bias |
| Up to 64 display / 256 method rows | Roadmap default, pilot-dependent; E4 adds information as well as a diagnostic |
| Canonical hash convention v1 | Ordered A/B float rows and normalized signed zero; cross-language agreement needs golden vectors |
| Names supplied as reviewed input | Structural validators cannot detect direction clues or secrets embedded in approved free text |
| Error card retained in E4 | Failed/ambiguous method cases must not disappear from evaluation |
| `causal_proof` representable in proposal | Allows production checker to detect explicit overclaims rather than hiding them as parser failures |
| No citation correctness claim yet | Registry validates availability; faithful attribution and release require Vaishak's checker |
| No automatic template repair | Malformed predictions remain observable failures |

External questions live in the shared document. Blocking points for integration:
Faizah's source-to-runtime mapping and export consumer; Anish's exact sample/hash
API; Vaishak's prediction/checker signatures and output fields. None blocks mocked
Phase 2 progress.

## Maintenance checklist

After each phase: update status and exact commands/results; link artifacts; record
changed assumptions; list remaining dependencies; distinguish local branch from
merged main. After an external handoff: record the revision and actual adapter
fixture run before changing “planned” to “integrated”. Keep research observations,
scripted fixtures and mathematical examples separately labeled.

## Latest verification record

12 November 2026, local branch `codex/kris-track-b-plan`, Python 3.12.13:

- `PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache bash scripts/check.sh`: PASS.
- 90 tests passed: 67 pre-existing plus 23 Phase 1 cases; overall coverage 90%.
- Ruff lint and formatting passed; original eight-case demo retained its expected
  four verified / three unsupported / one wrong-operation results.
- Source archive and wheel built successfully.
- Contract example generated with `python -m causalbridge.discovery.example`.
- No model calls, real ANM calculation or production checker execution occurred.
- Standalone independent artifact auditing remains Phase 3, not claimed complete.

Local work is not yet committed, pushed or merged. This record describes a tested
working tree, not remote main. Test counts are descriptive; acceptance depends on
invariants exercised and the documented limits, not counts or coverage alone.
