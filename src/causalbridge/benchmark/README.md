# Small synthetic model generation

`generate_dag` creates a NetworkX DAG with 2–8 explicit nodes named `N0`, `N1`,
etc. It accepts an exact edge count, a maximum in-degree, and an integer seed.
Impossible constraints raise `ValueError`. Isolated nodes stay in the graph.

`generate_cpts` accepts a valid 2–8 node `nx.DiGraph` and returns one existing
`causalbridge.schemas.CPT` per node. Generated parent IDs are sorted, row keys
follow that explicit order, and every probability lies in `[0.1, 0.9]`.

```python
from causalbridge.benchmark import generate_cpts, generate_dag
from causalbridge.schemas import Assumptions, RuntimeCase

graph = generate_dag(3, 2, 2, seed=42)
cpts = generate_cpts(graph, seed=43)
case = RuntimeCase(
    case_id="example_complete",
    graph_group_id="example",
    graph_nodes=tuple(graph.nodes),
    graph_edges=tuple(graph.edges),
    question="Does increasing N0 increase N1?",
    visible_cpts=cpts,
    assumptions=Assumptions(
        correct_dag=True,
        fully_observed=True,
        independent_noise=True,
        positivity=True,
    ),
)
```

This example illustrates schema compatibility. It does not certify an answer to
the question. Benchmark case labels and hidden oracle records require separate
validation before export.

`validate_witness` checks two complete `RuntimeCase` models against a specified
visible `JointDistribution` and optional visible CPT constraints. It requires the
same DAG and all specified visible evidence, then checks that the requested
effects differ (and, by default, have opposite signs).
It uses the repository's development intervention adapter. The known +0.30/−0.30
fixture is tested in `tests/test_benchmark_generator.py`; Anish's independent
calculation remains necessary before using that result as a research label.

The existing `tools/graph.py` remains the runtime structural API. Parent,
ancestor, descendant, and valid-adjustment-set queries extend it without moving
or changing `has_path` and `valid_adjustment`.

## Small question set

From the repository root, generate seven deterministic Track A questions across
two graph groups:

```bash
python -m causalbridge.benchmark.pilot
```

This writes visible runtime cases to `data/pilot/track_a_small.jsonl` and
evaluator-only labels and complete models to the git-ignored
`data/oracle/track_a_small.jsonl`. Run with the project's installed environment
or set `PYTHONPATH=src` for a source checkout. The questions cover graph-only,
observational-joint, and complete-CPT evidence, plus reachability and no-path
controls. Numeric and witness labels are marked `local_checked_awaiting_anish`;
structural controls are marked `structural_checked`. Do not treat this small set
as the planned 10-group validated pilot.
