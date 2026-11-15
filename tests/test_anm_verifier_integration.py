"""Real ANM artifacts consumed by Vaishak's unmodified merged verifier contract."""

from dataclasses import replace
from pathlib import Path
from random import Random

import pytest

from causalbridge.discovery import anm
from causalbridge.discovery.anm import execute_anm_request, load_anm_artifacts
from causalbridge.discovery.anm_requests import ANMConfig, save_anm_request
from causalbridge.discovery.schemas import (
    ANMResult,
    DirectionEvidence,
    DirectionPrediction,
    MethodDirectionClaim,
    canonical_digest,
)
from causalbridge.discovery.statistics import summarize_display_rows
from causalbridge.verifier.bindings import VerificationContext
from causalbridge.verifier.checks import check_prediction

pytest.importorskip("numpy")


@pytest.fixture
def artifacts(tmp_path):
    rng = Random(261)
    rows = []
    for _ in range(128):
        a = rng.uniform(-2, 2)
        rows.append([a, a**3 + rng.gauss(0, 0.2)])
    path = tmp_path / "anm"
    save_anm_request(
        rows,
        case_id="D001",
        ab_mapping_id="map-1",
        directory=path,
        config=ANMConfig(threshold=0.0, configuration_version="test-not-calibrated"),
    )
    execute_anm_request(path)
    return load_anm_artifacts(path), rows


def evidence_and_prediction(artifacts):
    saved, rows = artifacts
    displayed = rows[:32]
    evidence = DirectionEvidence(
        case_id=saved.request.case_id,
        package="E4",
        ab_mapping_id="map-1",
        mapping_seed=17,
        variable_labels=("Measurement A", "Measurement B"),
        display_rows=displayed,
        display_sampling_seed=261,
        summary=summarize_display_rows(displayed),
        method_result=saved.result,
    )
    prediction = DirectionPrediction(
        case_id=evidence.case_id,
        package_digest=evidence.package_digest,
        predicted_direction=saved.result.predicted_direction,
        abstained=saved.result.predicted_direction is None,
        reason_code="method_ambiguous" if saved.result.predicted_direction is None else None,
        claims=(
            MethodDirectionClaim(
                type="method_direction",
                evidence_ref="method_result",
                direction=saved.result.predicted_direction,
            ),
        ),
    )
    return evidence, prediction


def receipt(evidence, prediction, original_request):
    # Originals come from runtime storage. Never derive method_request from method_result.
    return VerificationContext(
        case_id=evidence.case_id,
        package_digest=evidence.package_digest,
        proposal_digest=prediction.proposal_digest,
        ab_mapping_id=evidence.ab_mapping_id,
        mapping_seed=evidence.mapping_seed,
        display_sample_digest=evidence.display_sample_digest,
        method_result_digest=canonical_digest(evidence.method_result.model_dump(mode="json")),
        method_request=original_request,
    )


def test_live_numeric_result_round_trips_with_independent_original_request(artifacts, monkeypatch):
    original, _ = artifacts
    evidence, prediction = evidence_and_prediction(artifacts)
    context = receipt(evidence, prediction, original.request)
    # JSON persistence stands in for Kris's actual S1 receipt storage.
    saved_context = VerificationContext.model_validate_json(context.model_dump_json())
    monkeypatch.setattr(anm, "execute_anm_request", lambda *args: pytest.fail("S2 ran ANM"))
    check = check_prediction(evidence, prediction, context=saved_context)
    assert check.status == "pass"
    assert check.release is True
    assert check.claim_findings[0].reason_code == "method_claim_consistent"
    assert original.request.sample_digest != evidence.display_sample_digest
    assert original.request.selected_row_count == 128
    assert evidence.summary.n_display == 32


def test_missing_original_request_cannot_be_replaced_by_result_provenance(artifacts):
    original, _ = artifacts
    evidence, prediction = evidence_and_prediction(artifacts)
    context = receipt(evidence, prediction, original.request).model_copy(
        update={"method_request": None}
    )
    check = check_prediction(evidence, prediction, context=context)
    assert check.status == "abstain"
    assert check.release is False
    assert "method_request_missing" in check.reason_codes


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("sample_digest", canonical_digest("other sample"), "method_sample_mismatch"),
        ("config_digest", canonical_digest("other config"), "method_config_mismatch"),
        ("method_version", "other-method", "method_config_mismatch"),
        ("configuration_version", "other-config", "method_config_mismatch"),
        ("sampling_seed", 262, "method_sampling_mismatch"),
        ("split_seed", 262, "method_sampling_mismatch"),
    ],
)
def test_self_consistent_candidate_is_checked_against_original_not_itself(
    artifacts, field, value, expected
):
    original, rows = artifacts
    raw = original.result.model_dump(mode="json")
    raw["provenance"][field] = value
    candidate = ANMResult.model_validate(raw)
    changed = replace(original, result=candidate)
    evidence, prediction = evidence_and_prediction((changed, rows))
    # Even if a result/package receipt is made for this candidate, the independent
    # original request still exposes substitution. Candidate provenance is not a receipt.
    check = check_prediction(
        evidence, prediction, context=receipt(evidence, prediction, original.request)
    )
    assert check.status == "fail"
    assert expected in check.reason_codes


def test_all_counts_are_bound_to_saved_input_partition(artifacts):
    original, rows = artifacts
    raw = original.result.model_dump(mode="json")
    raw["provenance"].update(selected_row_count=130, training_row_count=65, evaluation_row_count=65)
    changed = replace(original, result=ANMResult.model_validate(raw))
    evidence, prediction = evidence_and_prediction((changed, rows))
    check = check_prediction(
        evidence, prediction, context=receipt(evidence, prediction, original.request)
    )
    assert check.status == "fail"
    assert "method_sampling_mismatch" in check.reason_codes


def test_threshold_is_bound_even_when_scores_are_unchanged(artifacts):
    original, rows = artifacts
    raw = original.result.model_dump(mode="json")
    raw.update(
        threshold=None,
        decision=None,
        predicted_direction=None,
        reason_code="threshold_not_configured",
    )
    changed = replace(original, result=ANMResult.model_validate(raw))
    evidence, _ = evidence_and_prediction((changed, rows))
    prediction = DirectionPrediction(
        case_id=evidence.case_id,
        package_digest=evidence.package_digest,
        predicted_direction="A_to_B",
        abstained=False,
        claims=(),
    )
    check = check_prediction(
        evidence, prediction, context=receipt(evidence, prediction, original.request)
    )
    assert check.status == "fail"
    assert "method_config_mismatch" in check.reason_codes


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("case_id", "other-case", "method_case_mismatch"),
        ("ab_mapping_id", "other-map", "ab_mapping_mismatch"),
    ],
)
def test_original_case_and_mapping_are_bound(artifacts, field, value, code):
    original, _ = artifacts
    evidence, prediction = evidence_and_prediction(artifacts)
    raw = evidence.model_dump(mode="json")
    raw[field] = value
    if field == "ab_mapping_id":
        raw["method_result"]["provenance"][field] = value
    changed = DirectionEvidence.model_validate(raw)
    prediction = DirectionPrediction(
        **{
            **prediction.model_dump(),
            "case_id": changed.case_id,
            "package_digest": changed.package_digest,
        }
    )
    check = check_prediction(
        changed, prediction, context=receipt(changed, prediction, original.request)
    )
    assert check.status == "fail"
    assert code in check.reason_codes


def test_saved_numeric_request_connects_through_predictor_and_checker(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "anm_handshake", Path("examples/anm_integration.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.run_handshake(tmp_path / "handshake")
    assert summary["anm_status"] == "ok"
    assert summary["checker_status"] == "pass"
    assert summary["release"] is True
    assert (tmp_path / "handshake/anm/request.json").exists()
    assert (tmp_path / "handshake/verification_context.json").exists()
    assert (tmp_path / "handshake/S1.json").exists()
    assert (tmp_path / "handshake/S2.json").exists()
