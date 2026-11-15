"""A small, reproducible Track A question set with separate oracle records."""

import json
from pathlib import Path

import networkx as nx

from causalbridge.benchmark.generator import generate_cpts, generate_dag
from causalbridge.benchmark.witness import validate_witness
from causalbridge.schemas import CPT, Assumptions, JointDistribution, Query, RuntimeCase
from causalbridge.tools.graph import has_path
from causalbridge.tools.reference import intervention


def _assumptions() -> Assumptions:
    return Assumptions(
        correct_dag=True, fully_observed=True, independent_noise=True, positivity=True
    )


def _case(
    model: RuntimeCase,
    case_id: str,
    question: str,
    evidence_level: str,
    *,
    visible_cpts: tuple[CPT, ...] = (),
    visible_joint: JointDistribution | None = None,
) -> RuntimeCase:
    """Construct runtime input explicitly; never copy oracle fields into it."""
    return RuntimeCase(
        case_id=case_id,
        graph_group_id=model.graph_group_id,
        graph_nodes=model.graph_nodes,
        graph_edges=model.graph_edges,
        question=question,
        evidence_level=evidence_level,
        visible_cpts=visible_cpts,
        visible_joint=visible_joint,
        assumptions=model.assumptions,
    )


def _effect(model: RuntimeCase, query: Query) -> float:
    return intervention(model, query, query.to_value) - intervention(model, query, query.from_value)


def _oracle_row(
    case: RuntimeCase,
    query: Query,
    *,
    answerable: bool,
    gold_answer: bool | float | str | None,
    target_value: float | None,
    reason: str,
    models: tuple[RuntimeCase, ...],
    verification_status: str,
) -> dict:
    return {
        "case_id": case.case_id,
        "graph_group_id": case.graph_group_id,
        "query": query.model_dump(mode="json"),
        "answerable": answerable,
        "gold_answer": gold_answer,
        "target_value": target_value,
        "reason": reason,
        "verification_status": verification_status,
        "verification_evidence": (
            "tests/test_pilot_numerical_confirmation.py"
            if verification_status == "independently_checked"
            else "tests/test_benchmark_pilot.py"
        ),
        "oracle_models": [model.model_dump(mode="json") for model in models],
    }


def build_small_pilot() -> tuple[tuple[RuntimeCase, ...], tuple[dict, ...]]:
    """Return seven visible questions and evaluator-only records.

    Anish's independent rational and engine checks are in
    tests/test_pilot_numerical_confirmation.py.
    """
    assumptions = _assumptions()
    base = dict(
        graph_group_id="G001",
        graph_nodes=("X", "Y", "Z"),
        graph_edges=(("Z", "X"), ("Z", "Y"), ("X", "Y")),
        question="Does increasing X increase Y?",
        assumptions=assumptions,
    )
    common_cpts = (
        CPT(node="Z", parents=(), p_one={"": 0.5}),
        CPT(node="X", parents=("Z",), p_one={"0": 0.2, "1": 0.8}),
    )
    positive = RuntimeCase(
        case_id="G001_oracle_plus",
        visible_cpts=common_cpts
        + (
            CPT(
                node="Y",
                parents=("X", "Z"),
                p_one={"00": 0.6, "01": 0.1, "10": 0.9, "11": 0.4},
            ),
        ),
        **base,
    )
    negative = RuntimeCase(
        case_id="G001_oracle_minus",
        visible_cpts=common_cpts
        + (
            CPT(
                node="Y",
                parents=("X", "Z"),
                p_one={"00": 0.4, "01": 0.9, "10": 0.1, "11": 0.6},
            ),
        ),
        **base,
    )
    xy = JointDistribution(
        variables=("X", "Y"),
        probabilities={key: 0.25 for key in ("00", "01", "10", "11")},
    )
    sign_query = Query(cause="X", outcome="Y", question_type="effect_direction")
    validate_witness(positive, negative, None, sign_query)
    validate_witness(positive, negative, xy, sign_query)
    positive_effect = _effect(positive, sign_query)

    graph = generate_dag(3, 1, 1, seed=42)
    cpts = generate_cpts(graph, seed=43)
    source, target = next(iter(graph.edges))
    isolated = next(node for node in graph.nodes if node not in {source, target})
    generated = RuntimeCase(
        case_id="G002_oracle_base",
        graph_group_id="G002",
        graph_nodes=tuple(graph.nodes),
        graph_edges=tuple(graph.edges),
        question=f"What is the effect of changing {source} from 0 to 1 on {target}?",
        visible_cpts=cpts,
        assumptions=assumptions,
    )
    target_cpt = next(cpt for cpt in cpts if cpt.node == target)
    flipped_target = CPT(
        node=target,
        parents=target_cpt.parents,
        p_one={"0": target_cpt.p_one["1"], "1": target_cpt.p_one["0"]},
    )
    flipped = RuntimeCase(
        case_id="G002_oracle_flipped",
        graph_group_id="G002",
        graph_nodes=generated.graph_nodes,
        graph_edges=generated.graph_edges,
        question=generated.question,
        visible_cpts=tuple(flipped_target if cpt.node == target else cpt for cpt in cpts),
        assumptions=assumptions,
    )
    magnitude_query = Query(cause=source, outcome=target, question_type="effect_magnitude")
    validate_witness(generated, flipped, None, magnitude_query)
    generated_effect = _effect(generated, magnitude_query)

    rows = []

    def add(
        case: RuntimeCase,
        query: Query,
        answer: bool | float | str | None,
        reason: str,
        models: tuple[RuntimeCase, ...],
        *,
        target_value: float | None = None,
        structural: bool = False,
    ) -> None:
        rows.append(
            (
                case,
                _oracle_row(
                    case,
                    query,
                    answerable=answer is not None,
                    gold_answer=answer,
                    target_value=target_value,
                    reason=reason,
                    models=models,
                    verification_status=(
                        "structural_checked" if structural else "independently_checked"
                    ),
                ),
            )
        )

    add(
        _case(positive, "G001_sign_graph", positive.question, "graph_only"),
        sign_query,
        None,
        "opposite_effect_witness_with_same_graph",
        (positive, negative),
    )
    add(
        _case(positive, "G001_sign_xy", positive.question, "observational_joint", visible_joint=xy),
        sign_query,
        None,
        "opposite_effect_witness_with_same_visible_xy",
        (positive, negative),
    )
    add(
        _case(
            positive,
            "G001_sign_complete",
            positive.question,
            "complete_cpts",
            visible_cpts=positive.visible_cpts,
        ),
        sign_query,
        "positive",
        "complete_cpts_identify_effect",
        (positive,),
        target_value=positive_effect,
    )
    reach_query = Query(cause="X", outcome="Y", question_type="reachability")
    add(
        _case(positive, "G001_path", "Is there a directed path from X to Y?", "graph_only"),
        reach_query,
        has_path(positive, reach_query),
        "directed_path_is_visible_in_graph",
        (positive,),
        structural=True,
    )
    add(
        _case(generated, "G002_effect_graph", generated.question, "graph_only"),
        magnitude_query,
        None,
        "opposite_effect_witness_with_same_graph",
        (generated, flipped),
    )
    add(
        _case(
            generated,
            "G002_effect_complete",
            generated.question,
            "complete_cpts",
            visible_cpts=generated.visible_cpts,
        ),
        magnitude_query,
        generated_effect,
        "complete_cpts_identify_effect",
        (generated,),
        target_value=generated_effect,
    )
    no_path_query = Query(cause=isolated, outcome=target, question_type="effect_direction")
    if has_path(generated, no_path_query):
        raise RuntimeError("Expected generated isolated-node control")
    add(
        _case(
            generated,
            "G002_no_path",
            f"Does increasing {isolated} affect {target}?",
            "graph_only",
        ),
        no_path_query,
        "zero",
        "no_directed_path_implies_zero_total_effect",
        (generated,),
        target_value=0.0,
        structural=True,
    )
    return tuple(case for case, _ in rows), tuple(oracle for _, oracle in rows)


_FAMILIES = (
    ("G003", "mediation", ("X", "M", "Y"), (("X", "M"), ("M", "Y")), 38),
    ("G004", "collider", ("X", "Y", "Z"), (("X", "Y"), ("Z", "Y")), 40),
    (
        "G005",
        "confounded_mediation",
        ("X", "Y", "Z", "M"),
        (("Z", "X"), ("Z", "Y"), ("X", "M"), ("M", "Y")),
        50,
    ),
    ("G006", "direct_with_isolate", ("X", "Y", "Z"), (("X", "Y"),), 60),
    (
        "G007",
        "parallel_mediators",
        ("X", "Y", "M", "N"),
        (("X", "M"), ("X", "N"), ("M", "Y"), ("N", "Y")),
        70,
    ),
    (
        "G008",
        "confounded_mediator",
        ("X", "Y", "Z", "M"),
        (("Z", "X"), ("Z", "M"), ("X", "M"), ("M", "Y")),
        82,
    ),
    (
        "G009",
        "collider_with_descendant",
        ("X", "Y", "Z", "W"),
        (("X", "Y"), ("Z", "Y"), ("Y", "W")),
        90,
    ),
    (
        "G010",
        "upstream_confounder",
        ("W", "Z", "X", "Y"),
        (("W", "Z"), ("Z", "X"), ("X", "Y"), ("W", "Y")),
        100,
    ),
)


def build_track_a_pilot() -> tuple[tuple[RuntimeCase, ...], tuple[dict, ...]]:
    """Return the ten-group pilot: original seven cases plus eight graph families."""
    cases, labels = build_small_pilot()
    visible = list(cases)
    oracle = list(labels)
    by_id = {row["case_id"]: row for row in labels}
    known = by_id["G001_sign_graph"]
    known_models = tuple(RuntimeCase.model_validate(raw) for raw in known["oracle_models"])
    known_query = Query.model_validate(known["query"])
    known_cpts = tuple(cpt for cpt in known_models[0].visible_cpts if cpt.node != "Y")
    validate_witness(*known_models, None, known_query, visible_cpts=known_cpts)
    known_partial = _case(
        known_models[0],
        "G001_sign_partial",
        known_models[0].question,
        "partial_cpts",
        visible_cpts=known_cpts,
    )
    visible.append(known_partial)
    oracle.append(
        _oracle_row(
            known_partial,
            known_query,
            answerable=False,
            gold_answer=None,
            target_value=None,
            reason="opposite_effect_witness_with_same_visible_cpts",
            models=known_models,
            verification_status="independently_checked",
        )
    )

    sparse = by_id["G002_effect_complete"]
    sparse_model = RuntimeCase.model_validate(sparse["oracle_models"][0])
    sparse_query = Query.model_validate(sparse["query"])
    sparse_path_query = Query(
        cause=sparse_query.cause,
        outcome=sparse_query.outcome,
        question_type="reachability",
    )
    sparse_path = _case(
        sparse_model,
        "G002_path",
        f"Is there a directed path from {sparse_query.cause} to {sparse_query.outcome}?",
        "graph_only",
    )
    visible.append(sparse_path)
    oracle.append(
        _oracle_row(
            sparse_path,
            sparse_path_query,
            answerable=True,
            gold_answer=True,
            target_value=None,
            reason="directed_path_is_visible_in_graph",
            models=(sparse_model,),
            verification_status="structural_checked",
        )
    )
    sparse_models = tuple(
        RuntimeCase.model_validate(raw) for raw in by_id["G002_effect_graph"]["oracle_models"]
    )
    sparse_cpts = tuple(
        cpt for cpt in sparse_model.visible_cpts if cpt.node != sparse_query.outcome
    )
    validate_witness(*sparse_models, None, sparse_query, visible_cpts=sparse_cpts)
    sparse_partial = _case(
        sparse_model,
        "G002_effect_partial",
        sparse_model.question,
        "partial_cpts",
        visible_cpts=sparse_cpts,
    )
    visible.append(sparse_partial)
    oracle.append(
        _oracle_row(
            sparse_partial,
            sparse_query,
            answerable=False,
            gold_answer=None,
            target_value=None,
            reason="opposite_effect_witness_with_same_visible_cpts",
            models=sparse_models,
            verification_status="independently_checked",
        )
    )
    for row in oracle:
        if row["graph_group_id"] == "G001":
            row["graph_family"] = "confounded_direct"
        elif row["graph_group_id"] == "G002":
            row["graph_family"] = "sparse_direct_with_isolate"
            row["cpt_seed"] = 43

    for group_id, family, nodes, edges, seed in _FAMILIES:
        graph = nx.DiGraph()
        graph.add_nodes_from(nodes)
        graph.add_edges_from(edges)
        base = RuntimeCase(
            case_id=f"{group_id}_oracle_base",
            graph_group_id=group_id,
            graph_nodes=nodes,
            graph_edges=edges,
            question="Does changing X from 0 to 1 increase Y?",
            visible_cpts=generate_cpts(graph, seed=seed),
            assumptions=_assumptions(),
        )
        outcome_cpt = next(cpt for cpt in base.visible_cpts if cpt.node == "Y")
        opposite = CPT(
            node="Y",
            parents=outcome_cpt.parents,
            p_one={key: 1 - value for key, value in outcome_cpt.p_one.items()},
        )
        flipped = RuntimeCase(
            case_id=f"{group_id}_oracle_flipped",
            graph_group_id=group_id,
            graph_nodes=nodes,
            graph_edges=edges,
            question=base.question,
            visible_cpts=tuple(opposite if cpt.node == "Y" else cpt for cpt in base.visible_cpts),
            assumptions=base.assumptions,
        )
        query = Query(cause="X", outcome="Y", question_type="effect_direction")
        shared_cpts = tuple(cpt for cpt in base.visible_cpts if cpt.node != "Y")
        witness = validate_witness(base, flipped, None, query)
        validate_witness(base, flipped, None, query, visible_cpts=shared_cpts)
        if min(abs(witness.first_effect), abs(witness.second_effect)) < 0.05:
            raise ValueError(f"{group_id} effect is too close to zero for a pilot sign case")
        answer = "positive" if witness.first_effect > 0 else "negative"

        def add(
            suffix: str,
            question: str,
            evidence_level: str,
            case_query: Query,
            gold: bool | float | str | None,
            reason: str,
            models: tuple[RuntimeCase, ...],
            *,
            cpts: tuple[CPT, ...] = (),
            target: float | None = None,
            structural: bool = False,
            base_model: RuntimeCase = base,
            case_group_id: str = group_id,
            graph_family: str = family,
            cpt_seed: int = seed,
        ) -> None:
            case = _case(
                base_model,
                f"{case_group_id}_{suffix}",
                question,
                evidence_level,
                visible_cpts=cpts,
            )
            visible.append(case)
            row = _oracle_row(
                case,
                case_query,
                answerable=gold is not None,
                gold_answer=gold,
                target_value=target,
                reason=reason,
                models=models,
                verification_status="structural_checked" if structural else "independently_checked",
            )
            row.update(graph_family=graph_family, cpt_seed=cpt_seed)
            oracle.append(row)

        add(
            "sign_graph",
            base.question,
            "graph_only",
            query,
            None,
            "opposite_effect_witness_with_same_graph",
            (base, flipped),
        )
        add(
            "sign_partial",
            base.question,
            "partial_cpts",
            query,
            None,
            "opposite_effect_witness_with_same_visible_cpts",
            (base, flipped),
            cpts=shared_cpts,
        )
        add(
            "sign_complete",
            base.question,
            "complete_cpts",
            query,
            answer,
            "complete_cpts_identify_effect",
            (base,),
            cpts=base.visible_cpts,
            target=witness.first_effect,
        )
        path_query = Query(cause="X", outcome="Y", question_type="reachability")
        add(
            "path",
            "Is there a directed path from X to Y?",
            "graph_only",
            path_query,
            True,
            "directed_path_is_visible_in_graph",
            (base,),
            structural=True,
        )
        reverse_query = Query(cause="Y", outcome="X", question_type="effect_direction")
        if has_path(base, reverse_query):
            raise ValueError(f"{group_id} unexpectedly has a reverse path")
        add(
            "reverse_zero",
            "Does changing Y from 0 to 1 affect X?",
            "graph_only",
            reverse_query,
            "zero",
            "no_directed_path_implies_zero_total_effect",
            (base,),
            target=0.0,
            structural=True,
        )
    return tuple(visible), tuple(oracle)


def _write_pilot(runtime_path: Path, oracle_path: Path, cases, oracle) -> None:
    """Write visible cases and evaluator-only records into separate directories."""
    runtime_path, oracle_path = Path(runtime_path), Path(oracle_path)
    runtime_dir = runtime_path.parent.resolve()
    oracle_dir = oracle_path.parent.resolve()
    if (
        runtime_dir == oracle_dir
        or runtime_dir in oracle_dir.parents
        or oracle_dir in runtime_dir.parents
    ):
        raise ValueError("Runtime and oracle outputs must use separate directories")
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in oracle))
    runtime_path.write_text("".join(case.model_dump_json() + "\n" for case in cases))


def write_small_pilot(runtime_path: Path, oracle_path: Path) -> None:
    """Preserve the original seven-case development export."""
    _write_pilot(runtime_path, oracle_path, *build_small_pilot())


def write_track_a_pilot(runtime_path: Path, oracle_path: Path) -> None:
    """Export the ten-group pilot without putting oracle fields in runtime cases."""
    _write_pilot(runtime_path, oracle_path, *build_track_a_pilot())


if __name__ == "__main__":
    write_track_a_pilot(
        Path("data/pilot/track_a_10_groups.jsonl"),
        Path("data/oracle/track_a_10_groups.jsonl"),
    )
