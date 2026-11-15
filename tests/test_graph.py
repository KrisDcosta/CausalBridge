"""Graph contracts checked against explicit causal structures, without numeric evidence."""

import pytest

from causalbridge.schemas import Query, RuntimeCase
from causalbridge.tools.graph import has_path, valid_adjustment


def graph_case(edges, extra_nodes=()):
    return RuntimeCase(
        case_id="graph_contract",
        graph_nodes=tuple(sorted({"X", "Y", *extra_nodes, *(n for e in edges for n in e)})),
        graph_edges=tuple(edges),
        question="Graph operation for X and Y",
    )


@pytest.mark.parametrize(
    ("edges", "expected"),
    [
        pytest.param([("X", "Y")], True, id="direct"),
        pytest.param([("X", "M"), ("M", "Y")], True, id="mediated"),
        pytest.param([("Y", "X")], False, id="reverse-direction"),
        pytest.param([("Z", "X"), ("Z", "Y")], False, id="common-cause-only"),
        pytest.param([("X", "Z"), ("Y", "Z")], False, id="common-child-only"),
        pytest.param([], False, id="isolated-query-nodes"),
        pytest.param([("X", "M"), ("Z", "Y")], False, id="disconnected-components"),
        pytest.param(
            [("X", "A"), ("X", "B"), ("A", "Y"), ("B", "Y")],
            True,
            id="multiple-directed-paths",
        ),
    ],
)
def test_directed_reachability(edges, expected):
    case = graph_case(edges, extra_nodes=("I",))
    query = Query(cause="X", outcome="Y", question_type="reachability")
    assert has_path(case, query) is expected


@pytest.mark.parametrize(
    ("edges", "adjustment", "expected"),
    [
        pytest.param([("X", "Y")], (), True, id="unconfounded-empty-set"),
        pytest.param([], ("I",), True, id="isolated-adjustment-variable"),
        pytest.param(
            [("Z", "X"), ("Z", "Y"), ("X", "Y")],
            (),
            False,
            id="unblocked-confounding",
        ),
        pytest.param(
            [("Z", "X"), ("Z", "Y"), ("X", "Y")],
            ("Z",),
            True,
            id="confounder-blocks-backdoor",
        ),
        pytest.param([("X", "M"), ("M", "Y")], (), True, id="causal-path-is-not-backdoor"),
        pytest.param([("X", "M"), ("M", "Y")], ("M",), False, id="mediator-is-descendant"),
        pytest.param([("X", "Y"), ("X", "D")], ("D",), False, id="off-path-descendant"),
        pytest.param(
            [("A", "X"), ("A", "C"), ("B", "C"), ("B", "Y")],
            (),
            True,
            id="closed-collider-on-backdoor-path",
        ),
        pytest.param(
            [("A", "X"), ("A", "C"), ("B", "C"), ("B", "Y")],
            ("C",),
            False,
            id="conditioning-opens-collider",
        ),
        pytest.param(
            [("A", "X"), ("A", "C"), ("B", "C"), ("B", "Y"), ("C", "D")],
            ("D",),
            False,
            id="conditioning-on-collider-descendant-opens-path",
        ),
        pytest.param(
            [("A", "X"), ("A", "Y"), ("B", "X"), ("B", "Y")],
            ("A",),
            False,
            id="one-of-two-backdoor-paths-still-open",
        ),
        pytest.param(
            [("A", "X"), ("A", "Y"), ("B", "X"), ("B", "Y")],
            ("A", "B"),
            True,
            id="all-backdoor-paths-blocked",
        ),
    ],
)
def test_backdoor_criterion(edges, adjustment, expected):
    case = graph_case(edges, extra_nodes=("I",))
    query = Query(
        cause="X", outcome="Y", question_type="adjustment_validity", adjustment_set=adjustment
    )
    assert valid_adjustment(case, query) is expected


@pytest.mark.parametrize("operation", [has_path, valid_adjustment])
@pytest.mark.parametrize(
    "roles",
    [
        pytest.param({"cause": "unknown", "outcome": "Y"}, id="unknown-cause"),
        pytest.param({"cause": "X", "outcome": "unknown"}, id="unknown-outcome"),
        pytest.param(
            {"cause": "X", "outcome": "Y", "adjustment_set": ("unknown",)},
            id="unknown-adjustment-variable",
        ),
    ],
)
def test_graph_operations_reject_unknown_query_variables(operation, roles):
    case = graph_case([("X", "Y")])
    query = Query(question_type="adjustment_validity", **roles)
    with pytest.raises(ValueError, match="unknown graph variables"):
        operation(case, query)


def test_adjustment_check_preserves_graph_for_later_calls():
    case = graph_case([("Z", "X"), ("Z", "Y"), ("X", "Y")])
    query = Query(
        cause="X", outcome="Y", question_type="adjustment_validity", adjustment_set=("Z",)
    )
    before = case.model_dump_json()
    digest = case.evidence_digest()
    assert valid_adjustment(case, query) is True
    # Checking backdoors removes outgoing edges only in a temporary graph.
    assert has_path(case, query) is True
    assert valid_adjustment(case, query) is True
    assert case.model_dump_json() == before
    assert case.evidence_digest() == digest
