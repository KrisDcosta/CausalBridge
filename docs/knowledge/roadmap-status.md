# Roadmap: completed work versus remaining research

Snapshot: merged main through PR #6, plus the ten-group Track A pilot.
Sources: [detailed roadmap](../planning/Detailed_Implementation_Roadmap.pdf),
[working plan](../kris-track-b-plan.md), and the evidence-linked knowledge bank.
This is a capability/status map, not a percentage-complete claim. Passing synthetic
integration is distinct from completing the planned real-data experiment.

| Roadmap package | Owner | Evidence-backed status | Remaining |
| --- | --- | --- | --- |
| G1/G2 structural DAG utilities and backdoor checks | Arunima | Implemented and tested; used in the ten-group pilot | Live-case review / report |
| G3 exact insufficiency witness | Arunima + Anish | Same observed joint, opposite effects implemented; independent rational/engine confirmation extended to the ten-group pilot | Human review of new cases; live Track A run / report |
| N1 numerical intervention engine | Anish | Production engine merged; hand cases, reference comparisons and pilot confirmation tested | Use in final benchmark execution |
| N2 ANM diagnostic | Anish | Actual KRR/HSIC, pre-saved requests and error/ambiguity controls implemented; our native integration tested | Development threshold choice/freeze; real-data evaluation |
| D1 data audit/loader/source groups/splits | Faizah | No completed handoff observed in repo or shared planning folder | Audited snapshot, eligibility/exclusions, approved names, source-group splits, runtime/evaluator mapping |
| D2 E1–E4 evidence packages | Kris | Implemented and tested; matched rows/context, sampling, summaries and bindings | Exercise real loader output; review sanitized labels/units |
| V1 reusable predictor/adapter | Vaishak + Kris | Native single-call predictor integrated with our storage and prompts on synthetic data | Pinned live-model smoke |
| V2 process checker | Vaishak + Kris | Actual binding/typed-claim checker integrated; qualified disagreement and false attribution controls tested | Real-output error analysis; separate explanation audit if applicable |
| R1 S0/S1 execution and cached S2 | Kris | Durable attempts/raw replies, failures, resume/retries, model-free S2 and exports implemented/tested | Real-data/model execution under frozen protocol |
| Minimal baselines | Kris + Anish; scoring by Faizah | Simple-gate and ANM-only execution projections implemented | Faizah scorer-consumer acceptance and measured comparisons |
| E1 weighted metrics and group bootstrap | Faizah | Export boundary ready; actual scorer not observed | Hand-scored consumer fixture, weighted outcomes, paired source-group intervals |
| ALL pilot/held-out/report | Team | Software/synthetic handshake evidence available | Real 15–20-pair pilot if eligible; freeze; held-out execution; figures/error cases; final report/presentation |

## Kris's phase status

- Phase 0: scope/design defined.
- Phase 1: contracts, selection, matched packages and exact prompts implemented/tested.
- Phase 2: durable runner, cache/resume and S2 replay implemented/tested.
- Phase 3: separate artifact auditing and adversarial controls implemented/tested.
- Phase 4: available ANM/predictor/checker integration and provisional baseline/analysis
  handoffs implemented/tested; real loader/scorer acceptance still open.
- Phases 5–6: no live pilot, protocol freeze or held-out research run performed here.

## Scale and scientific claims

Track A now has 50 validated synthetic questions over ten graph groups. The
original seven-case set remains a development artifact. Track B's three synthetic integration
cases are not the planned 15–20 eligible observational pairs. H1 (names), H2
(method evidence) and H3 (checking) have experimental plumbing but no measured
real-model results yet. No positive/negative research conclusion is claimed.

## Current validation evidence

502 combined tests pass; lint/format, reference and production-engine demos,
Anish's real synthetic ANM handshake, and wheel/sdist builds pass. Our final native
three-case handshake saves 24 model-fixture replies and 12 S2 checks, resumes with
zero additional model calls, exports 51 analysis rows and passes its read-only audit.
LLM replies are scripted; ANM computation is real. These facts establish tested
software behavior, not causal-direction accuracy or checker benefit on real data.
