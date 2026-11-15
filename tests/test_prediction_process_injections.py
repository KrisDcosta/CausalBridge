"""Deliberate process corruptions, NOT naturally occurring prediction errors."""

import pytest

from causalbridge.discovery.schemas import DirectionEvidence, DirectionPrediction
from causalbridge.verifier.checks import check_prediction

OTHER = "sha256:" + "f" * 64


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("case_id", "other", "case_id_mismatch"),
        ("package_digest", OTHER, "package_digest_mismatch"),
    ],
)
def test_injected_prediction_binding_corruption(bound_direction, field, value, code):
    e, p, context = bound_direction()
    p = p.model_copy(update={field: value})
    result = check_prediction(e, p, context=context)
    assert result.status == "fail" and code in result.reason_codes


def test_replaced_s1_answer_is_not_released(bound_direction):
    e, p, context = bound_direction()
    p = p.model_copy(update={"predicted_direction": "B_to_A"})
    result = check_prediction(e, p, context=context)
    assert "proposal_digest_mismatch" in result.reason_codes and not result.release


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("sample_digest", OTHER, "method_sample_mismatch"),
        ("config_digest", OTHER, "method_config_mismatch"),
        ("ab_mapping_id", "swapped", "ab_mapping_mismatch"),
        ("sampling_seed", 9, "method_sampling_mismatch"),
        ("split_seed", 9, "method_sampling_mismatch"),
        ("method_version", "stale", "method_config_mismatch"),
        ("configuration_version", "stale", "method_config_mismatch"),
        ("threshold", 0.1, "method_config_mismatch"),
        ("case_id", "other", "method_case_mismatch"),
    ],
)
def test_injected_stale_request_bindings(bound_direction, field, value, code):
    e, p, context = bound_direction()
    request = context.method_request.model_copy(update={field: value})
    context = context.model_copy(update={"method_request": request})
    result = check_prediction(e, p, context=context)
    assert code in result.reason_codes and result.status == "fail"


def test_swapped_columns_even_with_rebound_proposal_fail_original_receipt(bound_direction):
    e, p, context = bound_direction(2, claims=[])
    data = e.model_dump(mode="json")
    data.update(ab_mapping_id="swapped", display_rows=[[b, a] for a, b in data["display_rows"]])
    swapped = DirectionEvidence.model_validate(data)
    p = p.model_copy(update={"package_digest": swapped.package_digest})
    result = check_prediction(swapped, p, context=context)
    assert "ab_mapping_mismatch" in result.reason_codes
    assert "display_sample_mismatch" in result.reason_codes
    assert not result.release


def test_forged_consistent_method_result_cannot_replace_saved_result(bound_direction):
    e, p, context = bound_direction()
    data = e.model_dump(mode="json")
    data["method_result"].update(
        score_ab=0.035,
        score_ba=0.012,
        margin=-0.023,
        decision="B_to_A",
        predicted_direction="B_to_A",
    )
    forged = DirectionEvidence.model_validate(data)
    p = DirectionPrediction.model_validate(
        p.model_dump(mode="json") | dict(package_digest=forged.package_digest, claims=[])
    )
    result = check_prediction(forged, p, context=context)
    assert "method_result_mismatch" in result.reason_codes and not result.release


def test_invalid_internal_method_result_is_revalidated(bound_direction):
    e, p, context = bound_direction()
    bad = e.method_result.model_copy(update={"margin": -1.0})
    corrupted = e.model_copy(update={"method_result": bad})
    result = check_prediction(corrupted, p, context=context)
    assert result.status == "fail" and result.reason_codes == ("invalid_evidence",)


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "B_to_A"},
        {"predicted_direction": None},
        {"threshold": None},
        {"status": "error"},
        {"score_ab": None},
        {"margin": -0.023},
    ],
)
def test_injected_inconsistent_anm_states_never_release(bound_direction, changes):
    e, p, context = bound_direction()
    e = e.model_copy(update={"method_result": e.method_result.model_copy(update=changes)})
    result = check_prediction(e, p, context=context)
    assert result.status == "fail" and result.reason_codes == ("invalid_evidence",)


def test_injected_split_count_mismatch(bound_direction):
    e, p, context = bound_direction()
    request = context.method_request.model_copy(
        update={"training_row_count": 2, "evaluation_row_count": 2}
    )
    context = context.model_copy(update={"method_request": request})
    assert "method_sampling_mismatch" in check_prediction(e, p, context=context).reason_codes


def test_injected_missing_cached_method(bound_direction):
    e, p, context = bound_direction()
    e = e.model_copy(update={"method_result": None})
    result = check_prediction(e, p, context=context)
    assert result.status == "fail" and result.reason_codes == ("invalid_evidence",)
