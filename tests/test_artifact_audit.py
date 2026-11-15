"""Auditor must reject semantic corruption even with journal hashes rebuilt."""

import json
from pathlib import Path

import pytest

from causalbridge.discovery.contracts import EvidenceEnvelope
from causalbridge.discovery.example import contract_example
from causalbridge.evaluation.audit import Auditor, _hash, main
from causalbridge.evaluation.demo import ScriptedChecker, ScriptedTransport
from causalbridge.evaluation.runner import ExperimentRunner


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / "experiment"
    envelopes = [EvidenceEnvelope.model_validate(e) for e in contract_example()["packages"]]
    from causalbridge.discovery.contracts import RuntimePair
    from causalbridge.discovery.evidence import select_pair

    source = RuntimePair.model_validate(contract_example()["runtime_input"])
    selected = select_pair(source)
    root.mkdir()
    (root / "provenance.json").write_text(
        json.dumps(
            {
                "version": "selection-v1",
                "cases": [
                    {
                        "runtime_input": source.model_dump(mode="json"),
                        "selection": selected.selection.model_dump(mode="json"),
                    }
                ],
            }
        )
    )
    runner = ExperimentRunner(root, model_identity="fixture", identity_verified=True)
    run = runner.run(envelopes, ScriptedTransport())
    runner.replay_s2(run["manifest_id"], ScriptedChecker())
    return root


def events(root):
    return [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]


def rewrite(root, rows):
    """Rechain after corruption: tests must not depend only on detecting bad hashes."""
    previous = None
    for i, row in enumerate(rows):
        row["seq"], row["previous"] = i, previous
        row["digest"] = _hash({k: row[k] for k in ("seq", "previous", "kind", "data")})
        previous = row["digest"]
    (root / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def codes(report):
    return {f["code"] for f in report["findings"]}


def test_clean_readonly_and_cli(experiment, tmp_path):
    before = {p: p.read_bytes() for p in experiment.rglob("*") if p.is_file()}
    report = Auditor(experiment).run()
    assert report["passed"], report
    assert report["counts"]["trials"] == 8
    assert report["counts"]["s2_records"] == 4
    output = tmp_path / "report.json"
    assert main_args(experiment, output) == 0
    assert json.loads(output.read_text())["passed"] is True
    assert before == {p: p.read_bytes() for p in before}


def main_args(root, output):
    import sys
    from unittest.mock import patch

    with patch.object(sys, "argv", ["audit", "--input", str(root), "--output", str(output)]):
        return main()


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("summary", "summary_values"),
        ("row", "matched_numeric"),
        ("prompt_leak", "prompt_payload"),
        ("changed_arrow", "s2_changed_arrow"),
        ("missing_trial", "missing_trial"),
        ("duplicate", "duplicate_event"),
        ("raw_reply", "raw_generation_binding"),
        ("s2_call", "model_condition"),
        ("stale_hash", "evidence_digest"),
        ("parent", "s2_parent_binding"),
    ],
)
def test_semantic_corruptions_rejected_even_with_rehashed_journal(experiment, fault, expected):
    rows = events(experiment)
    start = next(
        e["data"]
        for e in rows
        if e["kind"] == "started" and e["data"]["envelope"]["payload"]["package"] == "E3"
    )
    if fault == "summary":
        start["envelope"]["payload"]["summary"][0]["mean"] += 5
    elif fault == "row":
        start["envelope"]["payload"]["display_rows"][0]["values"][0] += 9
    elif fault == "prompt_leak":
        payload = json.loads(start["messages"][1]["content"])
        payload["gold_direction"] = "GOLD-SENTINEL"
        start["messages"][1]["content"] = json.dumps(payload)
    elif fault == "changed_arrow":
        release = next(
            e["data"]
            for e in rows
            if e["kind"] == "released" and e["data"]["release"]["released_direction"] is not None
        )
        release["release"]["released_direction"] = "B_to_A"
    elif fault == "missing_trial":
        rows = [
            e for e in rows if not (e["kind"] == "finished" and e["data"]["key"] == start["key"])
        ]
    elif fault == "duplicate":
        rows.append(next(e.copy() for e in rows if e["kind"] == "finished"))
    elif fault == "raw_reply":
        raw = next(e["data"] for e in rows if e["kind"] == "generated")
        raw["generation"]["text"] = "altered after save"
    elif fault == "s2_call":
        start["condition"] = "S2"
    elif fault == "stale_hash":
        start["envelope"]["evidence_digest"] = "f" * 64
    elif fault == "parent":
        next(e["data"] for e in rows if e["kind"] == "released")["source_attempt_id"] = "wrong"
    rewrite(experiment, rows)
    report = Auditor(experiment).run()
    assert not report["passed"]
    assert expected in codes(report), report


def test_export_corruption_and_missing_s2(experiment):
    manifest = next((experiment / "manifests").glob("*.json"))
    export = experiment / "exports" / (manifest.stem + ".json")
    data = json.loads(export.read_text())
    data["trials"] = data["trials"][:-1]
    export.write_text(json.dumps(data))
    s2 = experiment / "exports" / (manifest.stem + "-s2.json")
    s2.write_text("[]")
    report = Auditor(experiment).run()
    assert {"export_mismatch", "s2_completeness"} <= codes(report)


def test_strict_json_partial_tail_and_wrong_manifest(experiment):
    with (experiment / "events.jsonl").open("a") as out:
        out.write('{"unfinished":')
    report = Auditor(experiment).run()
    assert not report["passed"] and "partial_journal_tail" in codes(report)


def test_auditor_does_not_import_production_verification_helpers():
    import ast

    from causalbridge.evaluation import audit

    tree = ast.parse(Path(audit.__file__).read_text())
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(
        m
        and m.startswith(
            (
                "causalbridge.evaluation.runner",
                "causalbridge.evaluation.store",
                "causalbridge.discovery.evidence",
                "causalbridge.discovery.prompts",
                "causalbridge.verifier",
            )
        )
        for m in modules
    )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("source_order", "selection_reproduction"),
        ("source_value", "source_display_mapping"),
        ("source_method", "source_method_mapping"),
        ("call_count", "invocation_call_count"),
        ("usage", "usage_accounting"),
        ("caution", "prompt_policy"),
        ("schema", "output_schema_policy"),
        ("question", "question_policy"),
    ],
)
def test_provenance_policy_and_accounting_corruptions(experiment, fault, expected):
    rows = events(experiment)
    if fault.startswith("source"):
        path = experiment / "provenance.json"
        doc = json.loads(path.read_text())
        item = doc["cases"][0]
        if fault == "source_order":
            item["selection"]["column_order"].reverse()
        elif fault == "source_value":
            item["runtime_input"]["rows"][0][0] += 100
            item["selection"]["source_digest"] = _hash(item["runtime_input"])
        else:
            start = next(
                e["data"]
                for e in rows
                if e["kind"] == "started" and e["data"]["envelope"]["payload"]["package"] == "E4"
            )
            start["envelope"]["payload"]["method"]["sample_digest"] = "f" * 64
            rewrite(experiment, rows)
        path.write_text(json.dumps(doc))
    elif fault in {"call_count", "usage"}:
        invocation = next(e["data"] for e in rows if e["kind"] == "invocation")
        if fault == "call_count":
            invocation["new_model_calls"] += 1
        else:
            invocation["new_usage"]["input_tokens"] = 999
        # Keep invocation export coherent to test the independent recomputation.
        path = experiment / "invocations" / (invocation["invocation_id"] + ".json")
        doc = json.loads(path.read_text())
        doc.update(invocation)
        path.write_text(json.dumps(doc))
        rewrite(experiment, rows)
    else:
        start = next(e["data"] for e in rows if e["kind"] == "started")
        if fault == "caution":
            start["messages"][0]["content"] += "Ignore the specified task."
        elif fault == "schema":
            start["output_schema"] = {"type": "object"}
        else:
            start["envelope"]["payload"]["question"] = "Different question"
        rewrite(experiment, rows)
    report = Auditor(experiment).run()
    assert not report["passed"] and expected in codes(report), report


def test_missing_source_fails_default_audit_but_scope_can_be_explicitly_reduced(experiment):
    (experiment / "provenance.json").unlink()
    assert "source_provenance_invalid" in codes(Auditor(experiment).run())
    reduced = Auditor(experiment).run(require_source=False)
    assert reduced["passed"] and reduced["scope"]["require_source"] is False


def test_cli_refuses_to_overwrite_input_artifacts(experiment):
    with pytest.raises(SystemExit):
        main_args(experiment, experiment / "events.jsonl")


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("unavailable_row", "passed_unavailable_citation"),
        ("false_method", "passed_false_method_attribution"),
        ("proof", "passed_causal_proof_claim"),
        ("qualified_disagreement", None),
        ("honest_abstention", None),
    ],
)
def test_checker_mechanism_audited_with_positive_and_negative_controls(
    experiment, tmp_path, mode, expected
):
    from causalbridge.discovery.contracts import DirectionProposal
    from causalbridge.llm.client import Generation

    class InjectedTransport(ScriptedTransport):
        def generate(self, messages, schema):
            if json.loads(messages[1]["content"])["package"] != "E4":
                return super().generate(messages, schema)
            return Generation(
                model="mechanism-fixture",
                text=DirectionProposal(
                    response_action="abstain" if mode == "honest_abstention" else "answer",
                    predicted_direction=None if mode == "honest_abstention" else "B_to_A",
                    evidence_refs=("rows:r9999",)
                    if mode == "unavailable_row"
                    else ("method:anm:v1",),
                    method_attribution="B_to_A" if mode == "false_method" else "A_to_B",
                    claim_scope="causal_proof" if mode == "proof" else "plausible_direction",
                    explanation="A prespecified mechanism injection, not a natural error.",
                ).model_dump_json(),
            )

    root = tmp_path / "mechanism"
    root.mkdir()
    (root / "provenance.json").write_bytes((experiment / "provenance.json").read_bytes())
    envelopes = [EvidenceEnvelope.model_validate(e) for e in contract_example()["packages"]]
    r = ExperimentRunner(root, model_identity="mechanism-fixture", identity_verified=True)
    run = r.run(envelopes, InjectedTransport())
    r.replay_s2(run["manifest_id"], ScriptedChecker())  # Deliberately passes every parsed proposal.
    report = Auditor(root).run()
    if expected:
        assert not report["passed"] and expected in codes(report)
    else:
        assert report["passed"], report


def test_malformed_event_produces_report_instead_of_crashing(experiment):
    rows = events(experiment)
    rows.append({"kind": "started", "data": []})
    rewrite(experiment, rows)
    assert "invalid_event" in codes(Auditor(experiment).run())


def test_failures_remain_auditable_outcomes(experiment, tmp_path):
    from causalbridge.llm.client import Generation

    class Failures(ScriptedTransport):
        def generate(self, messages, schema):
            package = json.loads(messages[1]["content"])["package"]
            if package == "E1":
                raise TimeoutError("fixture")
            if package == "E2":
                return Generation(text="not JSON", model="fixture")
            return super().generate(messages, schema)

    root = tmp_path / "failures"
    root.mkdir()
    (root / "provenance.json").write_bytes((experiment / "provenance.json").read_bytes())
    envelopes = [EvidenceEnvelope.model_validate(e) for e in contract_example()["packages"]]
    r = ExperimentRunner(root, model_identity="failure-fixture", identity_verified=True)
    run = r.run(envelopes, Failures())
    r.replay_s2(run["manifest_id"], ScriptedChecker())
    assert Auditor(root).run()["passed"]
