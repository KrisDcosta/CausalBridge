"""Hand calculations, rational IPW cross-checks, evidence boundaries and integration."""

import json
import random
import subprocess
from fractions import Fraction
from itertools import product
from math import prod

import pytest

from causalbridge.demo import FixtureModel, demo_runs
from causalbridge.pipeline import CausalBridge
from causalbridge.schemas import Assumptions, Proposal, Query, RuntimeCase, ToolRequest
from causalbridge.tools.engine import CausalEngineBackend
from causalbridge.tools.inference import (
    backdoor_adjustment,
    check_evidence,
    compute_effect,
    compute_intervention,
)
from causalbridge.tools.reference import ReferenceBackend


def execute(case, query, operation, *, digest=None):
    request = ToolRequest(
        operation=operation,
        query=query,
        evidence_digest=case.evidence_digest() if digest is None else digest,
    )
    result = CausalEngineBackend().execute(request, case)
    assert result.request == request
    return result


@pytest.fixture
def confounded_model(assumptions):
    return RuntimeCase(
        case_id="confounded_cpts",
        graph_nodes=("Z", "X", "Y"),
        graph_edges=(("Z", "X"), ("Z", "Y"), ("X", "Y")),
        question="What is P(Y=1|do(X=1))?",
        assumptions=assumptions,
        visible_cpts=(
            {"node": "Z", "p_one": {"": 0.5}},
            {"node": "X", "parents": ["Z"], "p_one": {"0": 0.2, "1": 0.8}},
            {
                "node": "Y",
                "parents": ["X", "Z"],
                "p_one": {"00": 0.1, "01": 0.5, "10": 0.4, "11": 0.8},
            },
        ),
        visible_joint={
            "variables": ["Z", "X", "Y"],
            "probabilities": {
                "000": 0.36,
                "001": 0.04,
                "010": 0.06,
                "011": 0.04,
                "100": 0.05,
                "101": 0.05,
                "110": 0.08,
                "111": 0.32,
            },
        },
    )


@pytest.mark.parametrize("treatment,expected", [(0, 0.3), (1, 0.7)])
def test_toy_intervention_hand_calculation(toy, treatment, expected):
    query = Query(
        cause="X",
        outcome="Y",
        question_type="intervention_probability",
        intervention_value=treatment,
    )
    assert compute_intervention(toy, query) == pytest.approx(expected, abs=1e-12, rel=0)


@pytest.mark.parametrize("start,end,expected", [(0, 1, 0.3), (1, 0, -0.3)])
def test_confounded_effect_and_treatment_reversal(confounded_model, start, end, expected):
    # Average across Z: do(1)=.6, do(0)=.3, although observational P(Y=1|X=1)=.72.
    query = Query(
        cause="X",
        outcome="Y",
        question_type="effect_magnitude",
        from_value=start,
        to_value=end,
    )
    assert compute_effect(confounded_model, query) == pytest.approx(expected, abs=1e-12, rel=0)


@pytest.mark.parametrize("treatment,expected", [(0, 0.3), (1, 0.6)])
def test_backdoor_matches_hand_calculation(confounded_model, treatment, expected):
    query = Query(
        cause="X",
        outcome="Y",
        question_type="intervention_probability",
        intervention_value=treatment,
        adjustment_set=("Z",),
    )
    assert backdoor_adjustment(confounded_model, query) == pytest.approx(expected, abs=1e-12, rel=0)
    assert compute_intervention(confounded_model, query) == pytest.approx(
        expected, abs=1e-12, rel=0
    )


def test_mediation_hand_calculation(assumptions):
    case = RuntimeCase(
        case_id="mediation",
        graph_nodes=("X", "M", "Y"),
        graph_edges=(("X", "M"), ("M", "Y")),
        question="Effect of X on Y?",
        assumptions=assumptions,
        visible_cpts=(
            {"node": "X", "p_one": {"": 0.5}},
            {"node": "M", "parents": ["X"], "p_one": {"0": 0.2, "1": 0.8}},
            {"node": "Y", "parents": ["M"], "p_one": {"0": 0.1, "1": 0.9}},
        ),
    )
    query = Query(cause="X", outcome="Y", question_type="effect_magnitude")
    assert compute_effect(case, query) == pytest.approx(0.48, abs=1e-12, rel=0)


def test_ordering_and_treatment_mechanism_do_not_change_intervention(confounded_model):
    raw = confounded_model.model_dump()
    raw["graph_nodes"] = ["Y", "X", "Z"]
    raw["visible_cpts"][1]["p_one"] = {"0": 0.9, "1": 0.1}
    raw["visible_cpts"][2]["parents"] = ["Z", "X"]
    raw["visible_cpts"][2]["p_one"] = {"00": 0.1, "01": 0.4, "10": 0.5, "11": 0.8}
    # Drop the old joint: it belongs to the old treatment mechanism.
    raw["visible_joint"] = None
    reordered = RuntimeCase.model_validate(raw)
    query = Query(cause="X", outcome="Y", question_type="intervention_probability")
    assert compute_intervention(reordered, query) == pytest.approx(0.6, abs=1e-12, rel=0)


def test_path_can_have_zero_effect(toy):
    raw = toy.model_dump()
    raw["visible_cpts"][1]["p_one"] = {"0": 0.3, "1": 0.3}
    case = RuntimeCase.model_validate(raw)
    query = Query(cause="X", outcome="Y", question_type="effect_magnitude")
    assert compute_effect(case, query) == 0.0


def rational_joint(case):
    """Test-only observational distribution, with exact rational arithmetic."""
    rows = []
    for bits in product((0, 1), repeat=len(case.graph_nodes)):
        assignment = dict(zip(case.graph_nodes, bits, strict=True))
        factors = []
        for cpt in case.visible_cpts:
            key = "".join(str(assignment[p]) for p in cpt.parents)
            probability = Fraction(str(cpt.p_one[key]))
            factors.append(probability if assignment[cpt.node] else 1 - probability)
        rows.append((assignment, prod(factors)))
    assert sum(p for _, p in rows) == 1
    return rows


def ipw_oracle(case, treatment):
    """Independent identity: E[1(X=x)Y/P(X=x|parents(X))], using the full joint.

    Includes X's observational mechanism and divides by propensity; it does not
    call the engine, truncate the factorization, or use ReferenceBackend.
    """
    rows = rational_joint(case)
    treatment_cpt = next(c for c in case.visible_cpts if c.node == "X")
    answer = Fraction(0)
    for assignment, probability in rows:
        if assignment["X"] == treatment and assignment["Y"] == 1:
            key = "".join(str(assignment[p]) for p in treatment_cpt.parents)
            propensity = Fraction(str(treatment_cpt.p_one[key]))
            if treatment == 0:
                propensity = 1 - propensity
            answer += probability / propensity
    return answer


def generated_case(seed, size, assumptions):
    rng = random.Random(seed)
    nodes = ["Z", "X", *(f"M{i}" for i in range(size - 3)), "Y"]
    edges = {("Z", "X"), ("Z", "Y"), ("X", "Y")}
    for i, parent in enumerate(nodes):
        for child in nodes[i + 1 :]:
            if rng.random() < 0.25:
                edges.add((parent, child))
    cpts = []
    for node in nodes:
        parents = sorted(a for a, b in edges if b == node)
        cpts.append(
            {
                "node": node,
                "parents": parents,
                "p_one": {
                    "".join(map(str, bits)): rng.randint(1, 9) / 10
                    for bits in product((0, 1), repeat=len(parents))
                },
            }
        )
    return RuntimeCase(
        case_id=f"rational_{size}_{seed}",
        graph_nodes=tuple(reversed(nodes)),
        graph_edges=tuple(sorted(edges)),
        question="Effect of X on Y?",
        assumptions=assumptions,
        visible_cpts=tuple(cpts),
    )


@pytest.mark.parametrize("size", range(4, 9))
@pytest.mark.parametrize("seed", [261, 262])
def test_generated_dags_against_exact_rational_ipw(size, seed, assumptions):
    case = generated_case(seed, size, assumptions)
    query = Query(cause="X", outcome="Y", question_type="effect_magnitude")
    expected = {}
    for treatment in (0, 1):
        expected[treatment] = ipw_oracle(case, treatment)
        probability_query = Query(
            cause="X",
            outcome="Y",
            question_type="intervention_probability",
            intervention_value=treatment,
        )
        assert compute_intervention(case, probability_query) == pytest.approx(
            float(expected[treatment]), abs=1e-12, rel=0
        )
    assert compute_effect(case, query) == pytest.approx(
        float(expected[1] - expected[0]), abs=1e-12, rel=0
    )
    # Adjustment must also marginalize extra variables in a full observational joint.
    joint = rational_joint(case)
    raw = case.model_dump()
    raw["visible_cpts"] = []
    raw["visible_joint"] = {
        "variables": case.graph_nodes,
        "probabilities": {"".join(str(a[n]) for n in case.graph_nodes): float(p) for a, p in joint},
    }
    joint_case = RuntimeCase.model_validate(raw)
    for treatment in (0, 1):
        adjusted = Query(
            cause="X",
            outcome="Y",
            question_type="intervention_probability",
            intervention_value=treatment,
            adjustment_set=("Z",),
        )
        assert backdoor_adjustment(joint_case, adjusted) == pytest.approx(
            float(expected[treatment]), abs=1e-12, rel=0
        )


@pytest.mark.parametrize("operation", ["compute_effect", "compute_intervention"])
@pytest.mark.parametrize("evidence", ["none", "partial"])
def test_numeric_calls_reject_missing_cpts(toy, query, operation, evidence):
    raw = toy.model_dump()
    raw["visible_cpts"] = raw["visible_cpts"][:1] if evidence == "partial" else []
    limited = RuntimeCase.model_validate(raw)
    assert "complete_visible_cpts" in check_evidence(limited, query, operation)
    result = execute(limited, query, operation)
    assert result.value is None
    assert "complete_visible_cpts" in result.error


def test_structural_zero_needs_assumptions_but_no_cpts(assumptions):
    case = RuntimeCase(
        case_id="no_path",
        graph_nodes=("X", "Y"),
        graph_edges=(),
        question="Effect?",
        assumptions=assumptions,
    )
    query = Query(cause="X", outcome="Y", question_type="effect_magnitude")
    assert compute_effect(case, query) == 0.0
    raw = case.model_dump()
    raw["assumptions"] = None
    assert (
        "causal_assumptions"
        in execute(RuntimeCase.model_validate(raw), query, "compute_effect").error
    )
    # No path establishes zero contrast, not an absolute intervention probability.
    assert "complete_visible_cpts" in execute(case, query, "compute_intervention").error


@pytest.mark.parametrize("flag", [None, *Assumptions.model_fields])
@pytest.mark.parametrize(
    "operation", ["compute_effect", "compute_intervention", "backdoor_adjustment"]
)
def test_numeric_calls_require_all_causal_assumptions(toy, query, flag, operation):
    raw = toy.model_dump()
    if flag is None:
        raw["assumptions"] = None
    else:
        raw["assumptions"][flag] = False
    result = execute(RuntimeCase.model_validate(raw), query, operation)
    assert result.value is None
    assert "causal_assumptions" in result.error


def test_adjustment_rejects_missing_joint_and_invalid_sets(confounded_model):
    query = Query(cause="X", outcome="Y", question_type="intervention_probability")
    result = execute(confounded_model, query, "backdoor_adjustment")
    assert "valid_backdoor_adjustment_set" in result.error
    raw = confounded_model.model_dump()
    raw["visible_joint"] = {
        "variables": ["X", "Y"],
        "probabilities": {"00": 0.41, "01": 0.09, "10": 0.14, "11": 0.36},
    }
    query = Query(
        cause="X", outcome="Y", question_type="intervention_probability", adjustment_set=("Z",)
    )
    assert (
        "visible_joint_over_cause_outcome_adjustment"
        in execute(RuntimeCase.model_validate(raw), query, "backdoor_adjustment").error
    )


def test_empty_adjustment_allows_unconfounded_observational_substitution(toy):
    raw = toy.model_dump()
    raw["visible_cpts"] = []
    raw["visible_joint"] = {
        "variables": ["X", "Y"],
        "probabilities": {"00": 0.35, "01": 0.15, "10": 0.15, "11": 0.35},
    }
    query = Query(cause="X", outcome="Y", question_type="intervention_probability")
    assert backdoor_adjustment(RuntimeCase.model_validate(raw), query) == pytest.approx(0.7)


@pytest.mark.parametrize("size", [12, 13])
def test_enumeration_limit_is_explicit(toy, query, size):
    raw = toy.model_dump()
    extras = [f"I{i}" for i in range(size - 2)]
    raw["graph_nodes"] = [*raw["graph_nodes"], *extras]
    raw["visible_cpts"] = [*raw["visible_cpts"], *({"node": n, "p_one": {"": 0.5}} for n in extras)]
    result = execute(RuntimeCase.model_validate(raw), query, "compute_intervention")
    if size == 12:
        assert result.value == pytest.approx(0.7)
    else:
        assert result.value is None
        assert "at most 12 nodes" in result.error


def test_backend_rejects_stale_evidence_and_unknown_variables(toy, query):
    assert "Evidence digest mismatch" in execute(toy, query, "compute_effect", digest="old").error
    unknown = Query(cause="missing", outcome="Y", question_type="effect_magnitude")
    assert "unknown graph variables" in execute(toy, unknown, "compute_effect").error


def test_backend_revalidates_mutated_nested_evidence(toy, query):
    toy.visible_cpts[1].p_one["0"] = -0.1
    result = execute(toy, query, "compute_effect")
    assert result.value is None
    assert result.error is not None


def test_backend_preserves_visible_input_and_returns_floats(toy, query):
    before = toy.model_dump_json()
    result = execute(toy, query, "compute_effect")
    assert type(result.value) is float
    assert result.error is None
    assert toy.model_dump_json() == before


def test_both_backends_match_all_existing_demo_verdicts():
    engine = list(demo_runs(backend=CausalEngineBackend()))
    reference = list(demo_runs(backend=ReferenceBackend()))
    assert len(engine) == len(reference) == 8
    for actual, expected in zip(engine, reference, strict=True):
        assert actual.verdict.model_dump() == expected.verdict.model_dump()
        assert actual.tool_executed == expected.tool_executed


def test_pipeline_projects_hidden_data_and_abstains_without_numeric_execution(toy, query):
    raw = {
        **toy.model_dump(),
        "visible_cpts": [],
        "hidden_cpts": toy.model_dump()["visible_cpts"],
        "target_value": 0.4,
        "gold_response": "SECRET",
    }
    plan = Proposal(
        query=query, requested_operation="compute_effect", proposed_tool="compute_effect"
    )
    trace = CausalBridge(
        FixtureModel([plan.model_dump_json()]), CausalEngineBackend(), model_mode="scripted_fixture"
    ).run(RuntimeCase.from_benchmark(raw), query=query)
    assert trace.verdict.reason_code == "missing_evidence"
    assert trace.tool_executed is False
    assert "SECRET" not in trace.model_dump_json()
    # Direct backend calls must enforce the same boundary without the pipeline gate.
    assert (
        "complete_visible_cpts"
        in execute(RuntimeCase.from_benchmark(raw), query, "compute_effect").error
    )


def test_cli_selects_engine_for_demo(tmp_path):
    output = tmp_path / "engine.jsonl"
    proc = subprocess.run(
        ["causalbridge", "demo", "--backend", "engine", "--output", str(output)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 8
    assert sum(r["verdict"]["status"] == "verified" for r in rows) == 4


@pytest.mark.parametrize("function", [compute_effect, compute_intervention, backdoor_adjustment])
def test_public_numeric_functions_enforce_evidence_without_adapter(toy, query, function):
    raw = toy.model_dump()
    raw["visible_cpts"] = []
    with pytest.raises(ValueError, match="Missing preconditions"):
        function(RuntimeCase.model_validate(raw), query)


def test_backend_structural_result_types_and_graph_only_evidence(confounded_model):
    raw = confounded_model.model_dump()
    raw.update(visible_cpts=[], visible_joint=None, assumptions=None)
    case = RuntimeCase.model_validate(raw)
    query = Query(
        cause="X", outcome="Y", question_type="adjustment_validity", adjustment_set=("Z",)
    )
    for operation in ("has_directed_path", "is_valid_adjustment_set"):
        result = execute(case, query, operation)
        assert result.value is True
        assert result.error is None
    empty = Query(cause="X", outcome="Y", question_type="adjustment_validity")
    assert execute(case, empty, "is_valid_adjustment_set").value is False


def test_cli_run_selects_engine_with_scripted_model(toy, query, tmp_path, monkeypatch):
    from causalbridge import cli

    source, output = tmp_path / "case.jsonl", tmp_path / "trace.jsonl"
    source.write_text(toy.model_dump_json() + "\n")
    plan = Proposal(
        query=query, requested_operation="compute_effect", proposed_tool="compute_effect"
    )
    final = Proposal(**{**plan.model_dump(), "proposed_answer": "positive"})
    model = FixtureModel([query.model_dump_json(), plan.model_dump_json(), final.model_dump_json()])
    monkeypatch.setattr(cli, "OllamaModel", lambda config: model)
    calls = []

    class RecordingEngine(CausalEngineBackend):
        def execute(self, request, case):
            calls.append(request)
            return super().execute(request, case)

    monkeypatch.setattr(cli, "CausalEngineBackend", RecordingEngine)
    assert (
        cli.main(["run", "--backend", "engine", "--input", str(source), "--output", str(output)])
        == 0
    )
    assert len(calls) == 1
    trace = json.loads(output.read_text())
    assert trace["verdict"]["status"] == "verified"
    assert trace["tool_result"]["value"] == pytest.approx(0.4)
