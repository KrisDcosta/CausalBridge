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

Last remote snapshot observed: main `48d6cda` (PRs #1–#4), merged locally at `1163edf`.

| Workstream | Owner | Evidence-backed status | Evidence / next dependency |
| --- | --- | --- | --- |
| Known-DAG parsing, pipeline, contracts | Vaishak | Tested on audited main | Original Track A suite retained; see current verification record below |
| Exact reference graph/numeric backend | Existing development implementation; Anish owns production engine | Implemented and covered by original tests; production handoff not observed | `tools/reference.py`, `tools/graph.py`; development enumeration cap 12 nodes |
| Benchmark generation / exact witnesses | Arunima + Anish | Implemented small generator/witness/pilot; full benchmark and independent numeric validation pending | `benchmark/generator.py`, `witness.py`, `pilot.py`; 7 runtime cases in `data/pilot/track_a_small.jsonl`, 2 groups, exact witness joint; labels awaiting Anish |
| Tübingen ingestion and split audit | Faizah | Planned / handoff pending | No real-data loader in audited main |
| ANM | Anish | Output design supplied; tested implementation not observed | Shared collaboration document; our cards are scripted fixtures |
| Track B predictor / process checker | Vaishak | Implemented/tested merged | `llm/predictor.py`, `verifier/checks.py`, `verifier/bindings.py`; actual runner adapter not integrated |
| Evidence, prompts and execution | Kris | Phases 1–2 locally implemented/tested; real adapter integration pending | See phase tracker below |
| Scoring / intervals | Faizah | Planned / handoff pending | No scorer in audited main |
| Live pilot / held-out findings | Team | Not executed here | No research performance claims |

## Kris: plan versus actual work

| Phase | Current status | Actual deliverables | Remaining exit work |
| --- | --- | --- | --- |
| 0 Scope/design | Defined | Scope, architecture, research contrasts, phases and audit procedure; simplified shared questions | Maintain decisions as external handoffs arrive |
| 1 Contracts/evidence | Locally tested; integration pending | `discovery/contracts.py`, `evidence.py`, `prompts.py`, `example.py`; tests and contract example | External formats remain provisional; no teammate integration claim |
| 2 Runner/persistence | Locally implemented/tested | `evaluation/runner.py`, `store.py`, `demo.py`, tests and `docs/kris-phase2.md` | Production adapter remains Phase 4 |
| 3 Independent artifact audit | Planned | Test matrix specified; no standalone auditor yet | Separate reader plus deliberate corruption tests |
| 4 Integration | Planned | No real external adapters yet | Loader, ANM, predictor/checker and scorer consumer |
| 5 Pilot/freeze | Planned | None | Live model, audited pilot groups, budget review and frozen protocol |
| 6 Held-out/handoff | Planned | None | Frozen runs, independent audit and scoring reconciliation |

## Phase 1 behavior and files

- [Contracts](../../src/causalbridge/discovery/contracts.py): no evaluator fields;
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

Phase 1 was subsequently committed locally at `e8e0f90`, then remote main merged
at `1163edf`. Our work has not been pushed or merged to remote main. This record
describes local work, not remote main. Test counts are descriptive; acceptance depends on
invariants exercised and the documented limits, not counts or coverage alone.

## Phase 2 update — 14 November 2026

Reviewed remote main `48d6cda`: Arunima's small synthetic benchmark and exact witness
joint export, plus Vaishak's Track B schemas/predictor/checker and integration smoke,
are merged. Repository code is authoritative where the collaboration document's
older examples differ (e.g. directional_scores is not a current prediction field).
Anish's real ANM/independent numerical confirmation and Faizah's real loader/scorer
have not been observed here; this is not a claim they have done no work elsewhere.

Our Phase 2 implementation and reproducible demo are documented in
[kris-phase2.md](../kris-phase2.md). The runner stores all raw/parsed/failure outcomes,
process-locked journal events, manifests, per-invocation usage, retry lineage,
S2 parent links and cache identities. Fixture replay is complete; real Vaishak
adapter and ANM-request provenance remain Phase 4. Phase 3 independent artifact
auditing is next. No live experiment has been run.

### Phase 2 verification

- Full combined `PYTHONPATH=src UV_CACHE_DIR=/tmp/causalbridge-uv-cache bash scripts/check.sh`: 303 tests pass, lint/format pass, unchanged eight-case Track A demo, wheel/sdist build pass.
- 13 Phase 2 runner/storage test cases pass; 23 Phase 1 cases remain passing alongside the merged upstream suite.
- Final reproduction directory: `runs/kris-phase2-final` (ignored runtime artifacts).
  Manifest `8b4d098795aef586b37d9b1c1d23da249d1987784a089a1cb23a1496ecfe826b`:
  first invocation 24 calls / 12 S1 replay records; second invocation 0 new calls / 24 reused trials.
- Saved usage unknown for demo fixtures; counting tests use explicitly synthetic token values.
- Shared document now contains implemented answers beneath Kris's three original
  questions. Connector readback confirmed all three answers and unchanged other text.
- Phase 2 source/docs are committed locally with this update. No push/remote PR or
  real model/ANM/scoring run was performed. Phase 3 independent audit remains pending.
