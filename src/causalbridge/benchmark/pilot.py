"""A small, reproducible Track A question set with separate oracle records."""

import json
from pathlib import Path

from causalbridge.benchmark.generator import generate_cpts, generate_dag
from causalbridge.benchmark.witness import observational_marginal, validate_witness
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
        "oracle_models": [model.model_dump(mode="json") for model in models],
    }


def build_small_pilot() -> tuple[tuple[RuntimeCase, ...], tuple[dict, ...]]:
    """Return seven visible questions and evaluator-only records.

    Numeric and witness labels are locally checked but await Anish's independent
    engine calculation before being treated as final research ground truth.
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
    xy = observational_marginal(positive, ("X", "Y"))
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
                        "structural_checked" if structural else "local_checked_awaiting_anish"
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


def write_small_pilot(runtime_path: Path, oracle_path: Path) -> None:
    """Write public runtime cases and hidden oracle rows to separate directories."""
    runtime_path, oracle_path = Path(runtime_path), Path(oracle_path)
    runtime_dir = runtime_path.parent.resolve()
    oracle_dir = oracle_path.parent.resolve()
    if (
        runtime_dir == oracle_dir
        or runtime_dir in oracle_dir.parents
        or oracle_dir in runtime_dir.parents
    ):
        raise ValueError("Runtime and oracle outputs must use separate directories")
    cases, oracle = build_small_pilot()
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in oracle))
    runtime_path.write_text("".join(case.model_dump_json() + "\n" for case in cases))


if __name__ == "__main__":
    write_small_pilot(
        Path("data/pilot/track_a_small.jsonl"), Path("data/oracle/track_a_small.jsonl")
    )
