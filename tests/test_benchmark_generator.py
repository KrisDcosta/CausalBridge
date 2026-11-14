import networkx as nx
import pytest

from causalbridge.benchmark import (
    generate_cpts,
    generate_dag,
    observational_marginal,
    validate_witness,
)
from causalbridge.schemas import JointDistribution, Query, RuntimeCase, ToolRequest, bit_keys
from causalbridge.tools.reference import ReferenceBackend, intervention


@pytest.mark.parametrize("node_count", range(2, 9))
@pytest.mark.parametrize("seed", [0, 1, 17])
def test_generated_dags_are_reproducible_and_respect_constraints(node_count, seed):
    max_in_degree = min(2, node_count - 1)
    capacity = sum(min(max_in_degree, i) for i in range(node_count))
    for edge_count in (0, capacity // 2, capacity):
        graph = generate_dag(node_count, edge_count, max_in_degree, seed=seed)
        repeat = generate_dag(node_count, edge_count, max_in_degree, seed=seed)
        assert sorted(graph.nodes) == [f"N{i}" for i in range(node_count)]
        assert sorted(graph.edges) == sorted(repeat.edges)
        assert graph.number_of_edges() == edge_count
        assert nx.is_directed_acyclic_graph(graph)
        assert max(dict(graph.in_degree()).values()) <= max_in_degree


def test_isolated_nodes_are_preserved():
    graph = generate_dag(3, 0, 0, seed=2)
    assert sorted(graph.nodes) == ["N0", "N1", "N2"]
    assert list(graph.edges) == []


def test_cpts_use_schema_bit_keys_sorted_parents_and_bounds(assumptions):
    graph = nx.DiGraph()
    graph.add_nodes_from(["Y", "Z", "X", "I"])
    graph.add_edges_from([("Z", "Y"), ("X", "Y"), ("Z", "X")])
    tables = generate_cpts(graph, seed=11)
    assert tables == generate_cpts(graph, seed=11)
    assert [table.node for table in tables] == ["I", "X", "Y", "Z"]
    assert tables[2].parents == ("X", "Z")
    assert set(tables[2].p_one) == {"00", "01", "10", "11"}
    for table in tables:
        assert set(table.p_one) == bit_keys(len(table.parents))
        assert all(0.1 <= probability <= 0.9 for probability in table.p_one.values())
    case = RuntimeCase(
        case_id="generated",
        graph_nodes=tuple(graph.nodes),
        graph_edges=tuple(graph.edges),
        question="Does X affect Y?",
        visible_cpts=tables,
        assumptions=assumptions,
    )
    assert len(case.visible_cpts) == len(graph.nodes)
    assert RuntimeCase.from_benchmark(case.model_dump(mode="json")) == case
    query = Query(cause="X", outcome="Y", question_type="effect_magnitude")
    request = ToolRequest(
        operation="compute_effect", query=query, evidence_digest=case.evidence_digest()
    )
    result = ReferenceBackend().execute(request, case)
    assert result.error is None
    assert type(result.value) is float


@pytest.mark.parametrize(
    ("node_count", "edge_count", "max_in_degree", "seed"),
    [(1, 0, 0, 0), (9, 0, 0, 0), (3, 4, 2, 0), (3, 1, 0, 0), (3, -1, 1, 0), (True, 0, 0, 0)],
)
def test_invalid_dag_requests_rejected(node_count, edge_count, max_in_degree, seed):
    with pytest.raises(ValueError):
        generate_dag(node_count, edge_count, max_in_degree, seed=seed)


def test_cpt_generator_rejects_cycles_and_invalid_nodes():
    with pytest.raises(ValueError, match="DAG"):
        generate_cpts(nx.DiGraph([("X", "Y"), ("Y", "X")]), seed=0)
    with pytest.raises(ValueError, match="nonempty strings"):
        generate_cpts(nx.DiGraph([(1, "Y")]), seed=0)


def witness_models(assumptions):
    common = dict(
        graph_nodes=["X", "Y", "Z"],
        graph_edges=[["Z", "X"], ["Z", "Y"], ["X", "Y"]],
        question="Does increasing X increase Y?",
        assumptions=assumptions,
    )
    root_and_treatment = [
        {"node": "Z", "parents": [], "p_one": {"": 0.5}},
        {"node": "X", "parents": ["Z"], "p_one": {"0": 0.2, "1": 0.8}},
    ]
    positive = RuntimeCase.model_validate(
        {
            **common,
            "case_id": "M_plus",
            "visible_cpts": root_and_treatment
            + [
                {
                    "node": "Y",
                    "parents": ["X", "Z"],
                    "p_one": {"00": 0.6, "01": 0.1, "10": 0.9, "11": 0.4},
                }
            ],
        }
    )
    negative = RuntimeCase.model_validate(
        {
            **common,
            "case_id": "M_minus",
            "visible_cpts": root_and_treatment
            + [
                {
                    "node": "Y",
                    "parents": ["X", "Z"],
                    "p_one": {"00": 0.4, "01": 0.9, "10": 0.1, "11": 0.6},
                }
            ],
        }
    )
    return positive, negative


def test_confounded_witness_matches_visible_xy_and_opposite_effects(assumptions):
    positive, negative = witness_models(assumptions)
    visible = JointDistribution(
        variables=("X", "Y"), probabilities={key: 0.25 for key in ("00", "01", "10", "11")}
    )
    query = Query(cause="X", outcome="Y", question_type="effect_direction")
    assert observational_marginal(positive, ("X", "Y")).probabilities == pytest.approx(
        visible.probabilities
    )
    assert observational_marginal(negative, ("X", "Y")).probabilities == pytest.approx(
        visible.probabilities
    )
    assert intervention(positive, query, 1) == pytest.approx(0.65)
    assert intervention(positive, query, 0) == pytest.approx(0.35)
    assert intervention(negative, query, 1) == pytest.approx(0.35)
    assert intervention(negative, query, 0) == pytest.approx(0.65)
    result = validate_witness(positive, negative, visible, query)
    assert result.first_effect == pytest.approx(0.30)
    assert result.second_effect == pytest.approx(-0.30)


def test_witness_rejects_wrong_visible_evidence_or_same_effect(assumptions):
    positive, negative = witness_models(assumptions)
    query = Query(cause="X", outcome="Y", question_type="effect_direction")
    wrong = JointDistribution(
        variables=("X", "Y"),
        probabilities={"00": 0.24, "01": 0.26, "10": 0.25, "11": 0.25},
    )
    with pytest.raises(ValueError, match="visible evidence"):
        validate_witness(positive, negative, wrong, query)
    visible = observational_marginal(positive, ("X", "Y"))
    with pytest.raises(ValueError, match="insufficiently different"):
        validate_witness(positive, positive, visible, query)
    wrong_question = Query(cause="X", outcome="Y", question_type="reachability")
    with pytest.raises(ValueError, match="must ask for an effect"):
        validate_witness(positive, negative, visible, wrong_question)


def test_witness_checks_visible_cpt_constraints(assumptions):
    positive, negative = witness_models(assumptions)
    query = Query(cause="X", outcome="Y", question_type="effect_direction")
    shared = (positive.visible_cpts[0], positive.visible_cpts[1])
    assert validate_witness(positive, negative, None, query, visible_cpts=shared)
    with pytest.raises(ValueError, match="visible CPT evidence"):
        validate_witness(positive, negative, None, query, visible_cpts=(positive.visible_cpts[2],))
