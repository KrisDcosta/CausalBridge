"""State-machine tests with counting/failing transports and persisted replay."""

import json

import pytest

from causalbridge.discovery.contracts import DirectionProposal, EvidenceEnvelope, ReleaseRecord
from causalbridge.discovery.evidence import digest
from causalbridge.discovery.example import contract_example
from causalbridge.evaluation.runner import ExperimentRunner
from causalbridge.evaluation.store import Journal
from causalbridge.llm.client import Generation, ModelConfig


def packages():
    return [EvidenceEnvelope.model_validate(x) for x in contract_example()["packages"]]


class Model:
    def __init__(self, behavior="answer"):
        self.calls = 0
        self.behavior = behavior

    def generate(self, messages, schema):
        self.calls += 1
        if self.behavior == "timeout":
            raise TimeoutError("fixture outage")
        if self.behavior == "interrupt":
            raise KeyboardInterrupt()
        if self.behavior == "malformed":
            return Generation(text="not JSON", model="fixture")
        if self.behavior == "must_not_call":
            raise AssertionError("No model call permitted")
        proposal = DirectionProposal(
            response_action="abstain" if self.behavior == "abstain" else "answer",
            predicted_direction=None if self.behavior == "abstain" else "A_to_B",
            evidence_refs=(),
            method_attribution=None,
            claim_scope="plausible_direction",
            explanation="Scripted transport fixture; not empirical performance.",
        )
        return Generation(
            text=proposal.model_dump_json(), model="fixture", input_tokens=10, output_tokens=5
        )


class FixtureChecker:
    version = "fixture-checker-v1"

    def __init__(self):
        self.calls = 0

    def check(self, envelope, saved, receipt):
        self.calls += 1
        assert receipt["original_evidence_digest"] == envelope.evidence_digest
        assert receipt["parent_attempt_digest"] == digest(saved.model_dump(mode="json"))
        return ReleaseRecord(
            parent_attempt_id=saved.attempt_id,
            parent_attempt_digest=receipt["parent_attempt_digest"],
            checker_version=self.version,
            process_status="passed",
            response_action=saved.proposal.response_action,
            released_direction=saved.proposal.predicted_direction,
            reason_codes=("scripted_fixture_only",),
        )


# PredictionAttempt action lives on its proposal, not the transport record.
FixtureChecker.check.__doc__ = "Only orchestration is tested by this scripted checker."


def runner(path, **kwargs):
    return ExperimentRunner(
        path, model_identity="immutable-fixture-v1", identity_verified=True, **kwargs
    )


def test_full_24_call_experiment_and_disk_resume(tmp_path):
    from causalbridge.discovery.contracts import MethodCard, RuntimePair
    from causalbridge.discovery.evidence import build_packages, select_pair

    all_packages = []
    example = contract_example()
    for i in range(3):
        p = RuntimePair.model_validate(example["runtime_input"] | {"case_id": f"D{i + 1:04d}"})
        selected = select_pair(p)
        m = MethodCard.model_validate(
            example["packages"][3]["payload"]["method"]
            | {"sample_digest": selected.method_sample_digest}
        )
        all_packages.extend(build_packages(selected, m))
    model = Model()
    out = runner(tmp_path).run(all_packages, model)
    assert model.calls == out["new_model_calls"] == 24
    resumed = runner(tmp_path).run(all_packages, Model("must_not_call"))
    assert resumed["new_model_calls"] == 0
    assert resumed["trials"] == out["trials"]
    checker = FixtureChecker()
    releases = runner(tmp_path).replay_s2(out["manifest_id"], checker)
    assert checker.calls == len(releases) == 12
    assert all(r["release"] is not None for r in releases)
    assert runner(tmp_path).replay_s2(out["manifest_id"], checker) == releases
    assert checker.calls == 12
    for t in out["trials"]:
        assert t["outcome"]["attempt"]["input_tokens"] == 10
        assert t["start"]["messages"][1]["content"]
    assert (
        json.loads((tmp_path / "exports" / (out["manifest_id"] + ".json")).read_text()) == resumed
    )


@pytest.mark.parametrize(
    "behavior,status", [("timeout", "model_error"), ("malformed", "parse_error")]
)
def test_failed_trials_retained_and_not_checked_or_retried(tmp_path, behavior, status):
    out = runner(tmp_path).run(packages(), Model(behavior))
    assert len(out["trials"]) == 8
    assert all(t["outcome"]["attempt"]["status"] == status for t in out["trials"])
    if status == "parse_error":
        assert out["trials"][0]["outcome"]["attempt"]["raw_text"] == "not JSON"
    checker = FixtureChecker()
    releases = runner(tmp_path).replay_s2(out["manifest_id"], checker)
    assert checker.calls == 0
    assert all(r["skip_reason"] == "parent_prediction_failed" for r in releases)
    assert runner(tmp_path).run(packages(), Model("must_not_call"))["new_model_calls"] == 0


def test_interruption_is_unknown_and_never_automatically_retried(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        runner(tmp_path).run(packages()[:1], Model("interrupt"))
    out = runner(tmp_path).run(packages()[:1], Model())
    assert out["new_model_calls"] == 1  # S0 unknown; previously unscheduled S1 may run.
    assert out["trials"][0]["outcome"]["execution_error"] == "interrupted_unknown"
    assert out["trials"][0]["outcome"]["attempt"] is None


def test_raw_saved_before_parse_can_be_recovered_without_generation(tmp_path, monkeypatch):
    import causalbridge.evaluation.runner as module

    original = module._parse_attempt

    def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(module, "_parse_attempt", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner(tmp_path).run(packages()[:1], Model())
    monkeypatch.setattr(module, "_parse_attempt", original)
    out = runner(tmp_path).run(packages()[:1], Model())
    assert out["new_model_calls"] == 1
    assert out["trials"][0]["outcome"]["recovered"] is True
    assert out["trials"][0]["outcome"]["attempt"]["status"] == "parsed"


def test_partial_tail_quarantined_completed_corruption_rejected(tmp_path):
    r = runner(tmp_path)
    r.run(packages()[:1], Model())
    journal = tmp_path / "events.jsonl"
    with journal.open("ab") as out:
        out.write(b'{"unfinished":')
    assert r.run(packages()[:1], Model("must_not_call"))["new_model_calls"] == 0
    assert list(tmp_path.glob("quarantine-*.bin"))[0].read_bytes() == b'{"unfinished":'
    records = journal.read_text().splitlines()
    value = json.loads(records[0])
    value["data"]["model_identity"] = "tampered"
    records[0] = json.dumps(value)
    journal.write_text("\n".join(records) + "\n")
    with pytest.raises(ValueError, match="Corrupt completed"):
        r.run(packages()[:1], Model("must_not_call"))


def test_cache_invalidations_and_explicit_retry_parent(tmp_path, monkeypatch):
    import causalbridge.evaluation.runner as module

    r = runner(tmp_path)
    initial = r.run(packages()[:1], Model("timeout"))
    retry = r.run(packages()[:1], Model(), retry_id="manual-1")
    assert retry["new_model_calls"] == 2
    assert (
        retry["trials"][0]["start"]["parent_attempt_id"]
        == initial["trials"][0]["start"]["attempt_id"]
    )
    monkeypatch.setattr(module, "PROMPT_VERSION", "changed-v2")
    assert r.run(packages()[:1], Model())["new_model_calls"] == 2
    assert r.run(packages()[:1], Model(), replicate_id="second")["new_model_calls"] == 2
    other = ExperimentRunner(tmp_path, model_identity="different-model", identity_verified=True)
    assert other.run(packages()[:1], Model())["new_model_calls"] == 2


def test_unverified_identity_disables_cross_session_reuse(tmp_path):
    a = ExperimentRunner(tmp_path, model_identity="moving-model-tag")
    assert a.run(packages()[:1], Model())["new_model_calls"] == 2
    assert a.run(packages()[:1], Model("must_not_call"))["new_model_calls"] == 0
    b = ExperimentRunner(tmp_path, model_identity="moving-model-tag")
    assert b.run(packages()[:1], Model())["new_model_calls"] == 2


def test_duplicate_schedule_and_configuration_mismatch_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        runner(tmp_path).run([packages()[0], packages()[0]], Model())
    with pytest.raises(ValueError, match="configuration differs"):
        runner(tmp_path, config=ModelConfig()).run(packages(), Model())


def test_checker_errors_do_not_mutate_parent_or_release(tmp_path):
    class WrongChecker(FixtureChecker):
        def check(self, envelope, saved, receipt):
            return ReleaseRecord(
                parent_attempt_id=saved.attempt_id,
                parent_attempt_digest=receipt["parent_attempt_digest"],
                checker_version=self.version,
                process_status="passed",
                response_action="answer",
                released_direction="B_to_A",
                reason_codes=("wrong-arrow",),
            )

    out = runner(tmp_path).run(packages()[:1], Model())
    r = runner(tmp_path).replay_s2(out["manifest_id"], WrongChecker())
    assert r[0]["skip_reason"] == "checker_error" and r[0]["release"] is None
    resumed = runner(tmp_path).run(packages()[:1], Model("must_not_call"))
    assert resumed["trials"] == out["trials"]


def test_duplicate_journal_outcome_detected(tmp_path):
    store = Journal(tmp_path)
    with store.locked():
        store.append("finished", {"key": "same"})
        store.append("finished", {"key": "same"})
        with pytest.raises(ValueError, match="Duplicate"):
            store.by_key("finished")


def test_changed_evidence_schema_config_and_checker_version_invalidate(tmp_path, monkeypatch):
    import causalbridge.evaluation.runner as module
    from causalbridge.discovery.contracts import MethodCard, RuntimePair
    from causalbridge.discovery.evidence import build_packages, select_pair

    r = runner(tmp_path)
    original = packages()[2]
    out = r.run([original], Model())
    example = contract_example()
    p = RuntimePair.model_validate(
        example["runtime_input"]
        | {"variables": [{"name": "Changed semantic label"}, {"name": "Other label"}]}
    )
    s = select_pair(p)
    m = MethodCard.model_validate(
        example["packages"][3]["payload"]["method"] | {"sample_digest": s.method_sample_digest}
    )
    changed = build_packages(s, m)[2]
    assert r.run([changed], Model())["new_model_calls"] == 2
    schema = module.output_schema()
    monkeypatch.setattr(module, "output_schema", lambda: schema | {"description": "changed"})
    assert r.run([original], Model())["new_model_calls"] == 2
    model = Model()
    model.config = ModelConfig(seed=999)
    assert runner(tmp_path, config=model.config).run([original], model)["new_model_calls"] == 2
    checker = FixtureChecker()
    r.replay_s2(out["manifest_id"], checker)
    checker.version = "new-checker-version"
    r.replay_s2(out["manifest_id"], checker)
    assert checker.calls == 2


def test_model_abstention_and_usage_are_distinct_from_checker_errors(tmp_path):
    out = runner(tmp_path).run(packages()[:1], Model("abstain"))
    assert out["new_usage"] == {"input_tokens": 20, "output_tokens": 10}
    release = runner(tmp_path).replay_s2(out["manifest_id"], FixtureChecker())[0]
    assert release["release"]["process_status"] == "passed"
    assert release["release"]["released_direction"] is None
    cached = runner(tmp_path).run(packages()[:1], Model("must_not_call"))
    assert cached["new_usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert cached["historical_usage"] == {"input_tokens": 20, "output_tokens": 10}
    assert cached["monetary_cost"] is None
    assert len(list((tmp_path / "invocations").glob("*.json"))) == 2
