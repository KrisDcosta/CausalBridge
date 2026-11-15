# Data

Visible runtime cases belong in `pilot/`, `dev/` and `test/`. The committed
`pilot/track_a_10_groups.jsonl` is the validated synthetic Track A pilot. The
fixtures in `examples/` remain development examples.

Store cases as JSONL using `RuntimeCase` from `src/causalbridge/schemas.py`.
Include `case_id`, `graph_group_id`, explicit graph nodes and edges, question text,
visible probabilities and assumption flags. See [the integration guide](../docs/integration.md)
for the full format.

Complete models, reference answers and witness models belong in `oracle/`, which
is ignored except for its README. Export visible cases explicitly. Never pass
oracle records to a runtime model or tool. Join labels by case ID after execution.

Keep evidence pairs, paraphrases and isomorphic graph copies together. The proposed
split is 10 pilot, 18 development and 72 test graph groups, subject to pilot feasibility.
Freeze prompts, verifier rules and tolerances before generating the held-out test set.

`pilot/track_a_small.jsonl` remains the original seven-case development set.
`python -m causalbridge.benchmark.pilot` generates the 50-case, ten-group pilot
and writes evaluator-only records to ignored `oracle/track_a_10_groups.jsonl`.
Anish's rational calculation and numerical engine checks are exercised by
`tests/test_pilot_numerical_confirmation.py`; see [the pilot handoff](../docs/track_a_pilot.md).
