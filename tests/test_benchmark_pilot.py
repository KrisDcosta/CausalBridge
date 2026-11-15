import json

import pytest

from causalbridge.benchmark.pilot import (
    build_small_pilot,
    build_track_a_pilot,
    write_small_pilot,
    write_track_a_pilot,
)
from causalbridge.llm.client import Generation
from causalbridge.pipeline import CausalBridge
from causalbridge.schemas import Proposal, Query, RuntimeCase, ToolRequest
from causalbridge.tools.engine import CausalEngineBackend
from causalbridge.tools.reference import ReferenceBackend
from causalbridge.verifier.contracts import check_preconditions


def test_small_pilot_has_paired_questions_and_checked_labels():
    cases, oracle = build_small_pilot()
    by_id = {case.case_id: case for case in cases}
    labels = {row["case_id"]: row for row in oracle}
    assert len(cases) == len(oracle) == len(by_id) == 7
    assert {case.graph_group_id for case in cases} == {"G001", "G002"}
    assert by_id["G001_sign_graph"].question == by_id["G001_sign_xy"].question
    assert by_id["G001_sign_xy"].question == by_id["G001_sign_complete"].question
    assert by_id["G001_sign_xy"].visible_joint.probabilities == {
        key: 0.25 for key in ("00", "01", "10", "11")
    }
    assert by_id["G002_effect_graph"].question == by_id["G002_effect_complete"].question
    assert labels["G001_sign_graph"]["answerable"] is False
    assert labels["G001_sign_xy"]["answerable"] is False
    assert labels["G001_sign_complete"]["gold_answer"] == "positive"
    assert labels["G001_sign_complete"]["target_value"] == pytest.approx(0.30)
    assert labels["G001_path"]["gold_answer"] is True
    assert labels["G002_effect_graph"]["answerable"] is False
    assert type(labels["G002_effect_complete"]["gold_answer"]) is float
    assert labels["G002_effect_complete"]["target_value"] == pytest.approx(
        labels["G002_effect_complete"]["gold_answer"]
    )
    assert labels["G002_no_path"]["gold_answer"] == "zero"
    assert labels["G002_no_path"]["target_value"] == 0.0
    assert all(
        row["verification_status"] == "structural_checked"
        for row in oracle
        if row["case_id"] in {"G001_path", "G002_no_path"}
    )
    assert all(
        row["verification_status"] == "independently_checked"
        for row in oracle
        if row["case_id"] not in {"G001_path", "G002_no_path"}
    )


def test_runtime_export_keeps_oracle_out_of_cases_and_separate(tmp_path):
    public = tmp_path / "pilot" / "cases.jsonl"
    private = tmp_path / "oracle" / "labels.jsonl"
    write_small_pilot(public, private)
    cases = [json.loads(line) for line in public.read_text().splitlines()]
    oracle = [json.loads(line) for line in private.read_text().splitlines()]
    assert len(cases) == len(oracle) == 7
    assert {row["case_id"] for row in cases} == {row["case_id"] for row in oracle}
    assert all(RuntimeCase.model_validate(row).model_dump(mode="json") == row for row in cases)
    assert all("oracle_models" in row and "gold_answer" in row for row in oracle)
    for forbidden in ("gold_answer", "answerable", "target_value", "oracle_models", "query"):
        assert forbidden not in public.read_text()
    assert cases[0]["visible_cpts"] == []
    assert cases[1]["visible_joint"] is not None
    assert len(cases[2]["visible_cpts"]) == 3
    with pytest.raises(ValueError, match="separate directories"):
        write_small_pilot(public, public.with_name("oracle.jsonl"))
    with pytest.raises(ValueError, match="separate directories"):
        write_small_pilot(public, public.parent / "hidden" / "oracle.jsonl")


def test_runtime_model_prompts_cannot_receive_oracle_fields():
    cases, oracle = build_small_pilot()
    case = next(case for case in cases if case.case_id == "G001_sign_complete")
    hidden = next(row for row in oracle if row["case_id"] == case.case_id)
    raw = {**case.model_dump(mode="json"), **hidden, "secret_marker": "HIDDEN_ANSWER_KEY"}
    projected = RuntimeCase.from_benchmark(raw)
    query = Query.model_validate(hidden["query"])
    plan = Proposal(
        query=query, requested_operation="compute_effect", proposed_tool="compute_effect"
    )
    final = plan.model_copy(update={"proposed_answer": "positive"})

    class CaptureModel:
        def __init__(self):
            self.responses = iter((plan.model_dump_json(), final.model_dump_json()))
            self.messages = []

        def generate(self, messages, schema):
            self.messages.append(messages)
            return Generation(text=next(self.responses), model="test-fixture")

    model = CaptureModel()
    trace = CausalBridge(model, ReferenceBackend()).run(projected, query=query)
    assert trace.verdict.status == "verified"
    all_prompts = json.dumps(model.messages)
    for forbidden in ("HIDDEN_ANSWER_KEY", "secret_marker", "gold_answer", "oracle_models"):
        assert forbidden not in all_prompts
        assert forbidden not in trace.model_dump_json()


def test_answerability_agrees_with_existing_runtime_contracts():
    cases, oracle = build_small_pilot()
    for case, label in zip(cases, oracle, strict=True):
        query = Query.model_validate(label["query"])
        operation = (
            "has_directed_path" if query.question_type == "reachability" else "compute_effect"
        )
        request = ToolRequest(
            operation=operation, query=query, evidence_digest=case.evidence_digest()
        )
        missing = check_preconditions(request, case)
        result = ReferenceBackend().execute(request, case)
        if label["answerable"]:
            assert missing == ()
            assert result.error is None
            expected = label["target_value"]
            if query.question_type == "reachability":
                assert result.value is label["gold_answer"]
            elif expected is not None:
                assert result.value == pytest.approx(expected)
        else:
            assert "complete_visible_cpts" in missing
            assert result.error is not None


def test_generated_direct_effect_matches_cpt_rows():
    cases, oracle = build_small_pilot()
    case = next(case for case in cases if case.case_id == "G002_effect_complete")
    label = next(row for row in oracle if row["case_id"] == case.case_id)
    target = next(cpt for cpt in case.visible_cpts if cpt.node == "N2")
    assert target.parents == ("N0",)
    assert label["target_value"] == pytest.approx(target.p_one["1"] - target.p_one["0"])


def test_xy_only_case_cannot_use_backdoor_adjustment():
    cases, _ = build_small_pilot()
    case = next(case for case in cases if case.case_id == "G001_sign_xy")
    query = Query(
        cause="X", outcome="Y", question_type="intervention_probability", adjustment_set=("Z",)
    )
    request = ToolRequest(
        operation="backdoor_adjustment", query=query, evidence_digest=case.evidence_digest()
    )
    assert "visible_joint_over_cause_outcome_adjustment" in check_preconditions(request, case)
    assert ReferenceBackend().execute(request, case).error is not None


def test_ten_group_pilot_has_paired_evidence_and_diverse_graphs():
    cases, oracle = build_track_a_pilot()
    assert len(cases) == len(oracle) == 50
    assert len({case.case_id for case in cases}) == 50
    assert {case.graph_group_id for case in cases} == {f"G{i:03}" for i in range(1, 11)}
    assert {row["graph_family"] for row in oracle} >= {
        "confounded_direct",
        "mediation",
        "collider",
        "parallel_mediators",
        "direct_with_isolate",
    }
    assert len({tuple(sorted(case.graph_edges)) for case in cases}) >= 8
    assert sum(row["answerable"] for row in oracle) == 29
    assert sum(not row["answerable"] for row in oracle) == 21
    for group_id in {case.graph_group_id for case in cases}:
        group = [case for case in cases if case.graph_group_id == group_id]
        assert len(group) == 5
        assert len({tuple(case.graph_edges) for case in group}) == 1
        assert any(case.evidence_level == "graph_only" for case in group)
        assert any(case.evidence_level == "complete_cpts" for case in group)
        assert any(case.evidence_level in {"partial_cpts", "observational_joint"} for case in group)
    for case, label in zip(cases, oracle, strict=True):
        assert case.case_id == label["case_id"]
        assert RuntimeCase.from_benchmark({**case.model_dump(mode="json"), **label}) == case
        assert label["verification_evidence"].startswith("tests/")
        for raw in label["oracle_models"]:
            model = RuntimeCase.model_validate(raw)
            assert {cpt.node for cpt in model.visible_cpts} == set(case.graph_nodes)
            for cpt in model.visible_cpts:
                assert cpt.parents == tuple(sorted(cpt.parents))
                assert all(0.1 <= probability <= 0.9 for probability in cpt.p_one.values())


def test_ten_group_pilot_engine_answerability_and_hidden_export(tmp_path):
    public = tmp_path / "pilot" / "cases.jsonl"
    private = tmp_path / "oracle" / "labels.jsonl"
    write_track_a_pilot(public, private)
    cases = [RuntimeCase.model_validate_json(line) for line in public.read_text().splitlines()]
    labels = [json.loads(line) for line in private.read_text().splitlines()]
    assert len(cases) == len(labels) == 50
    second_public = tmp_path / "pilot2" / "cases.jsonl"
    second_private = tmp_path / "oracle2" / "labels.jsonl"
    write_track_a_pilot(second_public, second_private)
    assert public.read_bytes() == second_public.read_bytes()
    assert private.read_bytes() == second_private.read_bytes()
    for forbidden in (
        "gold_answer",
        "answerable",
        "target_value",
        "oracle_models",
        "query",
        "graph_family",
    ):
        assert forbidden not in public.read_text()
    backend = CausalEngineBackend()
    for case, label in zip(cases, labels, strict=True):
        query = Query.model_validate(label["query"])
        operation = (
            "has_directed_path" if query.question_type == "reachability" else "compute_effect"
        )
        request = ToolRequest(
            operation=operation, query=query, evidence_digest=case.evidence_digest()
        )
        result = backend.execute(request, case)
        if not label["answerable"]:
            assert result.value is None and result.error is not None
        elif query.question_type == "reachability":
            assert result.value is label["gold_answer"]
        else:
            assert result.error is None
            assert result.value == pytest.approx(label["target_value"], abs=1e-12)
