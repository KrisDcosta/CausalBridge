# Track A ten-group pilot handoff

This synthetic pilot contains 50 deterministic runtime questions from ten graph
groups. The original seven case IDs are retained. The new groups exercise mediation,
colliders, direct effects, confounding, parallel paths, descendants and isolates.
Five cases per group share a DAG and include an effect question under different
visible evidence, a complete-CPT answer, and structural controls. There are 29
answerable and 21 unanswerable cases. Graph sizes are three or four binary nodes.

`data/pilot/track_a_10_groups.jsonl` is the only input for the live Track A
model run. Each line is an existing `RuntimeCase` with explicit nodes and edges,
the question, assumptions, and visible evidence. Complete hidden models, query
specifications and labels are kept in the generated, git-ignored
`data/oracle/track_a_10_groups.jsonl`. The public export contains none of those
oracle fields. Do not pass the oracle file to `causalbridge run`.

## Generate and validate

```bash
uv run --extra anm python -m causalbridge.benchmark.pilot
uv run --extra anm pytest tests/test_benchmark_generator.py tests/test_benchmark_pilot.py tests/test_pilot_numerical_confirmation.py -q
```

The known observational witness has all four visible `P(X,Y)` cells equal to
one quarter and effects +0.30 and -0.30. The independent test uses rational
propensity reweighting, separate from both the development reference backend
and the benchmark's witness adapter, and compares Anish's engine. It also checks
every pilot oracle effect. The benchmark tests check evidence pairing, DAGs,
runtime answerability, deterministic export and absence of oracle fields.
`verification_status` and `verification_evidence` are evaluator-only metadata;
they describe these automated checks, not a recorded personal signoff on every
new question.

## Live run handoff

After Vaishak pins and smoke-tests the model/server, save its `ModelConfig` JSON
and run the existing CLI with the production engine:

```bash
uv run --extra anm causalbridge run \
  --input data/pilot/track_a_10_groups.jsonl \
  --output runs/track-a-pilot-live.jsonl \
  --backend engine \
  --config path/to/pinned-model-config.json
```

The command writes runtime traces only. Join their `runtime_case.case_id` to
the ignored oracle file after inference. Audit parsed queries, failures,
answerability, correct answers and valid abstentions by graph group and evidence
level. Freeze the model version, prompts, tolerances and generated cases before
comparing results. This repository does not contain a completed live Track A run;
the local Ollama endpoint was unavailable while preparing this handoff.
