"""Independent original requests: real input digests, durable ordering, no result fallback."""

import json

import pytest
from pydantic import ValidationError

from causalbridge.discovery.anm_requests import (
    ANMConfig,
    load_anm_request,
    save_anm_request,
)
from causalbridge.discovery.schemas import canonical_digest
from causalbridge.verifier.bindings import ANMRequestBinding


def rows(n=16):
    return [[float(i), float(i * i)] for i in range(n)]


def save(tmp_path, **kwargs):
    return save_anm_request(
        rows(), case_id="D001", ab_mapping_id="map-1", directory=tmp_path / "run", **kwargs
    )


def test_original_request_is_standalone_and_derived_from_actual_inputs(tmp_path):
    config = ANMConfig(minimum_rows=8, threshold=0.25, configuration_version="dev-frozen-1")
    request = save(tmp_path, config=config)
    path = tmp_path / "run"
    assert ANMRequestBinding.model_validate_json((path / "request.json").read_text()) == request
    assert request.sample_digest == canonical_digest({"ab_mapping_id": "map-1", "rows": rows()})
    assert request.config_digest == canonical_digest(config.model_dump(mode="json"))
    assert request.selected_row_count == 16
    assert request.training_row_count == request.evaluation_row_count == 8
    assert request.sampling_seed == request.split_seed == 261
    assert request.threshold == 0.25
    assert request.method_version == config.method_version
    assert request.configuration_version == "dev-frozen-1"
    assert not (path / "result.json").exists()
    original = load_anm_request(path)
    assert original.request == request
    assert set(original.training_indices).isdisjoint(original.evaluation_indices)
    assert sorted(original.training_indices + original.evaluation_indices) == list(range(16))


def test_request_save_never_needs_a_method_result_or_numpy(tmp_path, monkeypatch):
    import importlib

    def forbidden(*args, **kwargs):
        raise AssertionError("Saving original inputs must not import numerical methods")

    monkeypatch.setattr(importlib, "import_module", forbidden)
    assert save(tmp_path).selected_row_count == 16


def test_original_input_snapshot_survives_caller_mutation(tmp_path):
    original = rows()
    request = save_anm_request(
        original, case_id="D001", ab_mapping_id="map-1", directory=tmp_path / "run"
    )
    original[0][0] = -999.0
    assert load_anm_request(tmp_path / "run").sample.rows[0][0] == 0.0
    assert load_anm_request(tmp_path / "run").request == request


def test_request_directory_is_exclusive(tmp_path):
    save(tmp_path)
    before = (tmp_path / "run/request.json").read_bytes()
    with pytest.raises(FileExistsError):
        save(tmp_path)
    assert (tmp_path / "run/request.json").read_bytes() == before


@pytest.mark.parametrize(
    "invalid",
    [[], [[1, 2, 3]], [[True, 1.0]], [["1", 2]], [[float("nan"), 1]], [[1, float("inf")]]],
)
def test_invalid_transport_is_not_given_a_fabricated_original_digest(tmp_path, invalid):
    if not invalid:
        # An empty but well-formed sample can have a real digest and later yield a typed error.
        request = save_anm_request(
            invalid, case_id="D001", ab_mapping_id="map-1", directory=tmp_path / "run"
        )
        assert request.selected_row_count == 0
        return
    with pytest.raises(ValidationError):
        save_anm_request(invalid, case_id="D001", ab_mapping_id="map-1", directory=tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"threshold": -1.0},
        {"kernel_gamma": 0.0},
        {"ridge_alpha": 0.0},
        {"minimum_rows": 100, "maximum_rows": 8},
        {"split_seed": True},
        {"gold_direction": "A_to_B"},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValidationError):
        ANMConfig(**changes)


@pytest.mark.parametrize("filename", ["sample.json", "config.json", "request.json", "inputs.json"])
def test_changed_saved_inputs_do_not_pass_as_originals(tmp_path, filename):
    save(tmp_path)
    path = tmp_path / "run" / filename
    data = json.loads(path.read_text())
    if filename == "sample.json":
        data["rows"][0][0] = -1.0
    elif filename == "config.json":
        data["split_seed"] = 262
    elif filename == "request.json":
        data["case_id"] = "different-case"
    else:
        data["split_digest"] = canonical_digest("changed")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_anm_request(tmp_path / "run")


def test_request_loader_rejects_duplicate_keys(tmp_path):
    save(tmp_path)
    path = tmp_path / "run/request.json"
    text = path.read_text()
    path.write_text(text.replace('"case_id":"D001"', '"case_id":"D001","case_id":"other"'))
    with pytest.raises(ValueError, match="Duplicate"):
        load_anm_request(tmp_path / "run")


def test_same_data_seed_config_reproduce_all_original_identities(tmp_path):
    a = save(tmp_path / "a")
    b = save(tmp_path / "b")
    assert a == b
    assert (
        load_anm_request(tmp_path / "a/run").training_indices
        == load_anm_request(tmp_path / "b/run").training_indices
    )
    c = save(tmp_path / "c", config=ANMConfig(split_seed=262))
    assert c.sample_digest == a.sample_digest
    assert c.config_digest != a.config_digest
