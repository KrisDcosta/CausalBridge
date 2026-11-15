"""Offline integration smoke checks, using the existing scripted fixtures."""

import json
import runpy
from pathlib import Path

import pytest

from causalbridge.llm.predictor import PredictionExecution
from causalbridge.verifier.bindings import VerificationContext
from causalbridge.verifier.checks import PredictionCheck


@pytest.fixture
def smoke():
    return runpy.run_path(str(Path(__file__).parents[1] / "examples/track_b_integration.py"))


@pytest.mark.parametrize(
    "name,status,release",
    [
        ("E1", "pass", True),
        ("E2", "pass", True),
        ("E3", "pass", True),
        ("E4", "pass", True),
        ("E4_ambiguous", "pass", False),
        ("E4_unconfigured", "pass", False),
        ("E4_error", "pass", False),
        ("qualified_disagreement", "pass", True),
        ("false_method_attribution", "fail", False),
        ("missing_original_request", "abstain", False),
        ("saved_s1_abstention", "pass", False),
    ],
)
def test_existing_fixtures_through_predictor_and_saved_s1(smoke, name, status, release):
    records = {r["name"]: r for r in smoke["integration_records"]()}
    record = records[name]
    s0 = PredictionExecution.model_validate(record["S0"])
    s1 = PredictionExecution.model_validate(record["S1"])
    context = VerificationContext.model_validate(record["context"])
    result = PredictionCheck.model_validate(record["S2"])
    assert s0.prompt_condition.condition_id == "S0"
    assert s1.prompt_condition.condition_id == "S1"
    assert s0.package_digest == s1.package_digest == result.package_digest
    assert s1.prediction.proposal_digest == context.proposal_digest == result.proposal_digest
    assert json.loads(s1.generation.text) == s1.prediction.model_dump(mode="json")
    assert result.status == status and result.release is release
    assert record["model_calls"] == 2
    assert record["s2_source_run_id"] == s1.run_id


@pytest.mark.parametrize("failure", ["parse", "generate"])
def test_failures_are_saved_without_attempting_s2(smoke, monkeypatch, failure):
    from causalbridge.llm.client import Generation

    def failed_generate(self, messages, schema):
        self.calls += 1
        if failure == "generate":
            raise TimeoutError("offline fixture")
        return Generation(text="malformed response", model="scripted")

    def forbidden(*args, **kwargs):
        pytest.fail("S2 called on a failed prediction")

    monkeypatch.setattr(smoke["FixtureModel"], "generate", failed_generate)
    # runpy functions share a globals dictionary distinct from its returned copy.
    monkeypatch.setitem(smoke["integration_records"].__globals__, "check_prediction", forbidden)
    records = list(smoke["integration_records"]())
    assert len(records) == 11
    for record in records:
        assert record["S1"]["failure_stage"] == failure
        assert record["S2"] is None and record["s2_skip_reason"] == "prediction_failure"
        if failure == "parse":
            assert record["S1"]["generation"]["text"] == "malformed response"


def test_smoke_request_is_independent_of_returned_result(smoke):
    source = Path(__file__).parents[1] / "examples/track_b_phase1.jsonl"
    record = json.loads(source.read_text().splitlines()[3])
    request = smoke["original_request"](record)
    record["input"]["method_result"]["provenance"].update(
        sample_digest="sha256:" + "f" * 64,
        config_digest="sha256:" + "e" * 64,
        ab_mapping_id="swapped",
        selected_row_count=999,
        sampling_seed=99,
    )
    assert smoke["original_request"](record) == request


def test_smoke_has_no_network_and_cache_is_not_rewritten(smoke, monkeypatch):
    import socket

    from causalbridge.verifier.checks import check_prediction

    def forbidden(*args, **kwargs):
        pytest.fail("Offline smoke attempted network access")

    def observe(evidence, saved_prediction, *, context):
        before = saved_prediction.model_dump_json()
        result = check_prediction(evidence, saved_prediction, context=context)
        assert saved_prediction.model_dump_json() == before
        return result

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setitem(smoke["integration_records"].__globals__, "check_prediction", observe)
    assert all(r["model_calls"] == 2 for r in smoke["integration_records"]())
