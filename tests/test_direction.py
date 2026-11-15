import json

import pytest
from pydantic import ValidationError

from causalbridge.discovery.schemas import (
    ANMResult,
    DirectionEvidence,
    DirectionPrediction,
    PromptCondition,
)
from causalbridge.llm.client import Generation
from causalbridge.llm.predictor import predict_direction
from causalbridge.verifier.checks import check_prediction


def method_payload(**updates):
    return (
        dict(
            status="ok",
            score_ab=0.012,
            score_ba=0.035,
            margin=0.023,
            threshold=0.01,
            decision="A_to_B",
            predicted_direction="A_to_B",
            reason_code=None,
            provenance=dict(
                sample_digest="sha256:" + "a" * 64,
                ab_mapping_id="mapping-001",
                selected_row_count=4,
                training_row_count=3,
                evaluation_row_count=1,
                sampling_seed=261,
                split_seed=261,
                config_digest="sha256:" + "b" * 64,
                method_version="mock-1",
                configuration_version="dev-1",
                reproducibility_ref="sha256:" + "c" * 64,
                validation_findings=[],
                input_quality_warnings=[],
            ),
            limitations=["ANM assumptions may fail; confounding and feedback are not excluded."],
        )
        | updates
    )


def evidence_payload(package="E3", **updates):
    payload = dict(case_id="D0042", package=package, ab_mapping_id="mapping-001", mapping_seed=261)
    if package != "E2":
        payload.update(variable_labels=["Altitude", "Temperature"], units=["m", "C"])
    if package != "E1":
        payload.update(
            display_rows=[[205, 9.7], [46, 8.2]],
            display_sampling_seed=261,
            summary=dict(n_display=2, mean=[125.5, 8.95]),
        )
    if package == "E4":
        payload["method_result"] = method_payload()
    return payload | updates


def prediction(evidence, **updates):
    return (
        dict(
            case_id=evidence.case_id,
            package_digest=evidence.package_digest,
            predicted_direction="A_to_B",
            abstained=False,
            reason_code=None,
            claims=[],
        )
        | updates
    )


class Model:
    def __init__(self, response):
        self.response, self.calls = response, []

    def generate(self, messages, schema):
        self.calls.append((messages, schema))
        if isinstance(self.response, Exception):
            raise self.response
        return Generation(text=self.response, model="offline", input_tokens=12, output_tokens=8)


PROMPT = PromptCondition(condition_id="S1", version="runner-v1", instructions="Reason cautiously.")


@pytest.mark.parametrize("package", ["E1", "E2", "E3", "E4"])
def test_single_call_and_round_trip(package):
    evidence = DirectionEvidence.model_validate(evidence_payload(package))
    assert DirectionEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    model = Model(json.dumps(prediction(evidence)))
    trace = predict_direction(evidence, PROMPT, model)
    assert len(model.calls) == 1
    assert trace.failure_stage is None
    assert trace.prediction.predicted_direction == "A_to_B"
    assert trace.generation.text == model.response
    assert trace.generation.input_tokens == 12
    assert trace.package_digest == evidence.package_digest
    assert trace.prompt_condition == PROMPT
    assert "Which direction is more plausible" in model.calls[0][0][1]["content"]


def test_separate_identities_and_opaque_e2():
    e2 = DirectionEvidence.model_validate(evidence_payload("E2"))
    e3 = DirectionEvidence.model_validate(evidence_payload("E3"))
    e4 = DirectionEvidence.model_validate(evidence_payload("E4"))
    assert e2.display_sample_digest == e3.display_sample_digest == e4.display_sample_digest
    assert len({e2.package_digest, e3.package_digest, e4.package_digest}) == 3
    assert e4.method_result.provenance.sample_digest != e4.display_sample_digest
    assert e4.method_result.provenance.selected_row_count == 4
    assert "Altitude" not in e2.model_dump_json()
    changed = DirectionEvidence.model_validate(evidence_payload(display_rows=[[0, 1], [2, 3]]))
    assert changed.display_sample_digest != e3.display_sample_digest


@pytest.mark.parametrize(
    "package,updates",
    [
        ("E1", {"display_rows": [[1, 2]]}),
        ("E1", {"summary": {"n_display": 1}}),
        ("E2", {"variable_labels": ["secret", "B"]}),
        ("E2", {"units": ["m", "C"]}),
        ("E3", {"method_result": method_payload()}),
        ("E4", {"method_result": None}),
        ("E3", {"display_rows": []}),
        ("E3", {"variable_labels": None}),
        ("E3", {"display_rows": [[float("nan"), 1], [2, 3]]}),
        ("E3", {"summary": {"n_display": 3}}),
        (
            "E4",
            {
                "method_result": method_payload(
                    provenance=method_payload()["provenance"] | {"ab_mapping_id": "swapped"}
                )
            },
        ),
    ],
)
def test_invalid_evidence_rejected(package, updates):
    with pytest.raises(ValidationError):
        DirectionEvidence.model_validate(evidence_payload(package, **updates))


@pytest.mark.parametrize(
    "field",
    [
        "reference_direction",
        "gold_direction",
        "dataset_label",
        "source_group",
        "weight",
        "evaluator_metadata",
    ],
)
def test_runtime_rejects_evaluator_fields(field):
    with pytest.raises(ValidationError):
        DirectionEvidence.model_validate(evidence_payload(**{field: "secret"}))
    with pytest.raises(ValidationError):
        ANMResult.model_validate(method_payload(**{field: "secret"}))


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {
            "score_ab": 0.035,
            "score_ba": 0.012,
            "margin": -0.023,
            "decision": "B_to_A",
            "predicted_direction": "B_to_A",
        },
        {
            "threshold": 0.035 - 0.012,
            "decision": "abstain",
            "predicted_direction": None,
            "reason_code": "ambiguous_margin",
        },
        {
            "score_ab": 0.012,
            "score_ba": 0.012,
            "margin": 0.0,
            "threshold": 0.0,
            "decision": "abstain",
            "predicted_direction": None,
            "reason_code": "ambiguous_margin",
        },
        {
            "threshold": None,
            "decision": None,
            "predicted_direction": None,
            "reason_code": "threshold_not_configured",
        },
        {
            "status": "error",
            "score_ab": None,
            "score_ba": None,
            "margin": None,
            "decision": None,
            "predicted_direction": None,
            "reason_code": "constant_column",
            "error_category": "input_validation",
        },
    ],
)
def test_anm_states(updates):
    result = ANMResult.model_validate(method_payload(**updates))
    assert ANMResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "updates",
    [
        {"score_ab": None},
        {"score_ab": float("inf")},
        {"margin": -0.023},
        {"threshold": -0.01},
        {"decision": "B_to_A"},
        {"predicted_direction": None},
        {"threshold": None},
        {"status": "error", "reason_code": "fit_failed"},
        {"score_ab": True},
        {"probability": 0.9},
    ],
)
def test_incoherent_anm_rejected(updates):
    with pytest.raises(ValidationError):
        ANMResult.model_validate(method_payload(**updates))


@pytest.mark.parametrize(
    "updates",
    [
        {"predicted_direction": "positive"},
        {"abstained": True},
        {"predicted_direction": None},
        {"score_ab": 0.2},
        {"probability": 0.9},
    ],
)
def test_invalid_prediction_rejected(updates):
    e = DirectionEvidence.model_validate(evidence_payload())
    with pytest.raises(ValidationError):
        DirectionPrediction.model_validate(prediction(e, **updates))


@pytest.mark.parametrize(
    "response,stage",
    [
        ("not json", "parse"),
        ('{"case_id":"a","case_id":"b"}', "parse"),
        (TimeoutError("offline"), "generate"),
    ],
)
def test_failures_preserve_trace_without_retry(response, stage):
    e = DirectionEvidence.model_validate(evidence_payload())
    model = Model(response)
    trace = predict_direction(e, PROMPT, model)
    assert len(model.calls) == 1
    assert trace.failure_stage == stage
    assert trace.prediction is None and trace.error
    assert (trace.generation is not None) == isinstance(response, str)


@pytest.mark.parametrize(
    "updates", [{"case_id": "other"}, {"package_digest": "sha256:" + "d" * 64}]
)
def test_prediction_binding_mismatch(updates):
    e = DirectionEvidence.model_validate(evidence_payload())
    trace = predict_direction(e, PROMPT, Model(json.dumps(prediction(e, **updates))))
    assert trace.failure_stage == "binding"
    assert trace.prediction is not None  # retain parsed, rejected output for audit


def test_abstention_qualified_disagreement_and_missing_checker_context():
    e = DirectionEvidence.model_validate(evidence_payload("E4"))
    p = DirectionPrediction.model_validate(
        prediction(
            e,
            predicted_direction="B_to_A",
            claims=[
                {"type": "method_direction", "evidence_ref": "method_result", "direction": "A_to_B"}
            ],
        )
    )
    before = p.model_dump_json()
    result = check_prediction(e, p)
    assert result.status == "abstain" and not result.release
    assert result.reason_codes == ("verification_context_missing", "claim_binding_unverified")
    assert result.proposal_digest == p.proposal_digest
    assert before == p.model_dump_json()
    abstain = DirectionPrediction.model_validate(
        prediction(e, predicted_direction=None, abstained=True, reason_code="insufficient_evidence")
    )
    trace = predict_direction(e, PROMPT, Model(abstain.model_dump_json()))
    assert trace.prediction.abstained and trace.failure_stage is None


def test_orientation_seed_must_be_recorded_and_changes_display_identity():
    payload = evidence_payload()
    payload.pop("mapping_seed")
    with pytest.raises(ValidationError):
        DirectionEvidence.model_validate(payload)
    e = DirectionEvidence.model_validate(evidence_payload())
    changed = DirectionEvidence.model_validate(evidence_payload(mapping_seed=42))
    assert e.display_sample_digest != changed.display_sample_digest


def test_exact_request_survives_transport_mutation():
    e = DirectionEvidence.model_validate(evidence_payload())

    class MutatingModel:
        def generate(self, messages, schema):
            messages[0]["content"] = "changed"
            schema["properties"]["case_id"]["title"] = "changed"
            return Generation(text=json.dumps(prediction(e)), model="mock")

    trace = predict_direction(e, PROMPT, MutatingModel())
    assert trace.request_messages[0]["content"] != "changed"
    assert trace.output_schema["properties"]["case_id"]["title"] != "changed"


def test_actual_ollama_transport_is_single_structured_call():
    import httpx

    from causalbridge.llm.client import ModelConfig, OllamaModel

    e = DirectionEvidence.model_validate(evidence_payload("E2"))
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": json.dumps(prediction(e))},
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        trace = predict_direction(e, PROMPT, OllamaModel(ModelConfig(seed=42), client=client))
    assert trace.failure_stage is None and len(requests) == 1
    assert requests[0]["format"] == DirectionPrediction.model_json_schema()
    assert trace.generation_config.seed == 42
    assert trace.generation.output_tokens == 5


@pytest.mark.parametrize(
    "updates",
    [
        {"selected_row_count": 9},
        {"selected_row_count": True},
        {"sample_digest": "bad"},
        {"config_digest": "bad"},
        {"reproducibility_ref": "mutable-url"},
        {"reference_direction": "A_to_B"},
    ],
)
def test_invalid_method_provenance(updates):
    payload = method_payload()
    payload["provenance"].update(updates)
    with pytest.raises(ValidationError):
        ANMResult.model_validate(payload)


def test_checker_rejects_false_claims_without_trusting_missing_context():
    e = DirectionEvidence.model_validate(evidence_payload("E1"))
    p = DirectionPrediction.model_validate(
        prediction(
            e,
            claims=[
                {
                    "type": "method_direction",
                    "evidence_ref": "method_result",
                    "direction": "A_to_B",
                },
                {
                    "type": "display_row",
                    "evidence_ref": "display_rows",
                    "row_index": 90,
                    "values": [1.0, 2.0],
                },
            ],
        )
    )
    result = check_prediction(e, p)
    assert result.status == "fail" and not result.release
    assert "method_unavailable" in result.reason_codes
    assert "rows_unavailable" in result.reason_codes


def test_offline_demo_emits_all_conditions_and_method_states():
    from causalbridge.discovery.demo import demo_records

    records = list(demo_records())
    assert {r["input"]["package"] for r in records} == {"E1", "E2", "E3", "E4"}
    assert len(records) == 7
    assert all(r["execution"]["failure_stage"] is None for r in records)
    assert all(not r["check"]["release"] for r in records)


def test_reported_margin_tolerance_cannot_create_direction_from_equal_scores():
    with pytest.raises(ValidationError):
        ANMResult.model_validate(
            method_payload(
                score_ab=0.1,
                score_ba=0.1,
                margin=5e-13,
                threshold=0.0,
            )
        )


def test_demo_method_threshold_matches_linked_configuration():
    from causalbridge.discovery.demo import demo_records
    from causalbridge.discovery.schemas import canonical_digest

    for record in demo_records():
        method = record["input"]["method_result"]
        if method is None:
            continue
        repro = record["mock_reproducibility_record"]
        assert method["threshold"] == repro["config"]["threshold"]
        assert method["provenance"]["config_digest"] == canonical_digest(repro["config"])
        assert method["provenance"]["reproducibility_ref"] == canonical_digest(repro)
