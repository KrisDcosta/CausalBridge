"""ANM numerics and execution artifacts; full checks install the optional anm extra."""

import json
import subprocess
from random import Random

import pytest

from causalbridge.discovery import anm
from causalbridge.discovery.anm import execute_anm_request, load_anm_artifacts
from causalbridge.discovery.anm_requests import ANMConfig, load_anm_request, save_anm_request
from causalbridge.discovery.schemas import canonical_digest
from causalbridge.discovery.statistics import summarize_display_rows

np = pytest.importorskip("numpy")


def synthetic_rows(n=256, seed=261, *, linear=False):
    rng = Random(seed)
    pairs = []
    for _ in range(n):
        a = rng.gauss(0, 1) if linear else rng.uniform(-2, 2)
        b = (a if linear else a**3) + rng.gauss(0, 0.2)
        pairs.append([a, b])
    return pairs


def prepare(tmp_path, *, rows=None, config=None):
    path = tmp_path / "run"
    save_anm_request(
        synthetic_rows() if rows is None else rows,
        case_id="D001",
        ab_mapping_id="map-1",
        directory=path,
        config=config,
    )
    return path


def test_original_request_is_durable_before_method_starts(tmp_path, monkeypatch):
    path = prepare(tmp_path)
    before = (path / "request.json").read_bytes()

    def calculation(saved, record):
        assert (path / "inputs.json").exists()
        assert (path / "execution_started.json").exists()
        assert not (path / "result.json").exists()
        assert load_anm_request(path).request == saved.request
        assert saved.request.threshold is None
        return 0.125, 0.25

    monkeypatch.setattr(anm, "_calculate", calculation)
    result = execute_anm_request(path)
    assert result.status == "ok"
    assert result.reason_code == "threshold_not_configured"
    assert result.decision is result.predicted_direction is None
    assert (path / "request.json").read_bytes() == before
    assert load_anm_artifacts(path).request == load_anm_request(path).request


@pytest.mark.parametrize(
    "scores,tau,expected",
    [
        ((0.125, 0.5), 0.25, "A_to_B"),
        ((0.5, 0.125), 0.25, "B_to_A"),
        ((0.25, 0.5), 0.25, "abstain"),
        ((0.5, 0.25), 0.25, "abstain"),
        ((0.5, 0.5), 0.0, "abstain"),
    ],
)
def test_symmetric_threshold_and_closed_boundaries(tmp_path, monkeypatch, scores, tau, expected):
    path = prepare(tmp_path, config=ANMConfig(threshold=tau))
    monkeypatch.setattr(anm, "_calculate", lambda saved, record: scores)
    result = execute_anm_request(path)
    assert result.decision == expected
    assert result.predicted_direction == (None if expected == "abstain" else expected)
    assert result.reason_code == ("ambiguous_margin" if expected == "abstain" else None)


def test_nonlinear_control_and_column_swap(tmp_path):
    original = synthetic_rows()
    a = execute_anm_request(prepare(tmp_path / "a", rows=original, config=ANMConfig(threshold=0.0)))
    b = execute_anm_request(
        prepare(
            tmp_path / "b", rows=[pair[::-1] for pair in original], config=ANMConfig(threshold=0.0)
        )
    )
    assert a.status == b.status == "ok"
    assert a.predicted_direction == "A_to_B"
    assert b.predicted_direction == "B_to_A"
    assert a.score_ab == pytest.approx(b.score_ba, abs=1e-12, rel=0)
    assert a.margin == pytest.approx(-b.margin, abs=1e-12, rel=0)


def test_linear_gaussian_control_permits_ambiguity_without_claiming_identification(tmp_path):
    result = execute_anm_request(
        prepare(tmp_path, rows=synthetic_rows(linear=True), config=ANMConfig(threshold=1.0))
    )
    assert result.status == "ok"
    assert result.decision == "abstain"
    assert result.reason_code == "ambiguous_margin"
    assert any("not causal proof" in limitation for limitation in result.limitations)


def test_hsic_matches_explicit_centering_matrix_reference():
    x = np.array([-2.0, -0.7, 0.2, 0.8, 2.0])
    y = np.array([1.2, -0.5, 0.3, -0.2, 2.5])
    score, bandwidths = anm._hsic(x, y)
    h = np.eye(len(x)) - np.ones((len(x), len(x))) / len(x)
    kernels = []
    for vector, sigma in zip((x, y), bandwidths, strict=True):
        kernel = np.array(
            [
                [np.exp(-((float(a) - float(b)) ** 2) / (2 * sigma**2)) for b in vector]
                for a in vector
            ]
        )
        kernels.append(h @ kernel @ h)
    expected = np.trace(kernels[0] @ kernels[1]) / len(x) ** 2
    assert score == pytest.approx(float(expected), abs=1e-14, rel=0)


def test_training_scaling_is_not_fitted_on_evaluation_rows(tmp_path):
    path = prepare(tmp_path)
    saved = load_anm_request(path)
    data = np.array(saved.sample.rows)
    result = execute_anm_request(path)
    repro = load_anm_artifacts(path).reproducibility
    expected = data[list(saved.training_indices)]
    assert repro["preprocessing"]["training_means"] == pytest.approx(expected.mean(axis=0))
    assert repro["preprocessing"]["training_population_stds"] == pytest.approx(expected.std(axis=0))
    assert result.provenance.reproducibility_ref == canonical_digest(repro)
    assert set(repro["preprocessing"]["directions"]) == {"A_to_B", "B_to_A"}


@pytest.mark.parametrize(
    "rows,config,reason",
    [
        ([], ANMConfig(), "insufficient_rows"),
        ([[float(i), float(i * i)] for i in range(8)], ANMConfig(), "insufficient_rows"),
        ([[1.0, float(i)] for i in range(100)], ANMConfig(), "insufficient_variation"),
        (synthetic_rows(257), ANMConfig(), "too_many_rows"),
        (synthetic_rows(), ANMConfig(training_fraction=0.999), "insufficient_split_rows"),
    ],
)
def test_well_formed_unusable_samples_return_saved_typed_errors(tmp_path, rows, config, reason):
    path = prepare(tmp_path, rows=rows, config=config)
    result = execute_anm_request(path)
    assert result.status == "error"
    assert result.reason_code == reason
    assert result.error_category == "input_validation"
    assert result.score_ab is result.score_ba is result.margin is None
    assert result.decision is result.predicted_direction is None
    assert load_anm_artifacts(path).result == result


@pytest.mark.parametrize(
    "category,reason",
    [
        ("configuration", "numpy_unavailable"),
        ("regression", "regression_fit_failed"),
        ("dependence", "undefined_kernel_bandwidth"),
    ],
)
def test_method_failures_keep_original_request(tmp_path, monkeypatch, category, reason):
    path = prepare(tmp_path)
    original = (path / "request.json").read_bytes()

    def failure(*args):
        raise anm._DiagnosticError(category, reason)

    monkeypatch.setattr(anm, "_calculate", failure)
    result = execute_anm_request(path)
    assert result.status == "error"
    assert result.error_category == category
    assert result.reason_code == reason
    assert (path / "request.json").read_bytes() == original
    assert load_anm_artifacts(path).result == result


def test_execution_cannot_overwrite_or_rerun_an_attempt(tmp_path, monkeypatch):
    path = prepare(tmp_path)
    execute_anm_request(path)
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    monkeypatch.setattr(
        anm, "_calculate", lambda *args: pytest.fail("Repeated numerical execution")
    )
    with pytest.raises(FileExistsError):
        execute_anm_request(path)
    assert before == {p.name: p.read_bytes() for p in path.iterdir()}


def test_interrupted_attempt_requires_new_directory(tmp_path, monkeypatch):
    path = prepare(tmp_path)
    (path / "execution_started.json").write_text("{}")
    monkeypatch.setattr(anm, "_calculate", lambda *args: pytest.fail("Interrupted attempt rerun"))
    with pytest.raises(FileExistsError):
        execute_anm_request(path)


def test_no_original_request_fallback_from_returned_result(tmp_path):
    path = prepare(tmp_path)
    execute_anm_request(path)
    (path / "request.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_anm_artifacts(path)


def test_reproducibility_record_and_result_substitution_are_rejected(tmp_path):
    path = prepare(tmp_path)
    execute_anm_request(path)
    record_path = path / "reproducibility.json"
    record = json.loads(record_path.read_text())
    record["config"]["ridge_alpha"] = 42.0
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_anm_artifacts(path)
    # Updating the result's self-reported digest cannot change the original config.
    result_path = path / "result.json"
    result = json.loads(result_path.read_text())
    result["provenance"]["reproducibility_ref"] = canonical_digest(record)
    result_path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="inputs do not match"):
        load_anm_artifacts(path)


def test_cli_saves_request_and_executes_without_model_or_labels(tmp_path):
    source = tmp_path / "sample.json"
    source.write_text(
        json.dumps({"case_id": "D001", "ab_mapping_id": "map-1", "rows": synthetic_rows()})
    )
    proc = subprocess.run(
        ["causalbridge", "anm-run", "--input", str(source), "--output", str(tmp_path / "run")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    assert result["reason_code"] == "threshold_not_configured"
    assert load_anm_artifacts(tmp_path / "run").request.case_id == "D001"


def test_cli_rejects_evaluator_fields_before_saving(tmp_path):
    from causalbridge.cli import main

    source = tmp_path / "sample.json"
    source.write_text(
        json.dumps(
            {"case_id": "D001", "ab_mapping_id": "map-1", "rows": [], "gold_direction": "A_to_B"}
        )
    )
    assert main(["anm-run", "--input", str(source), "--output", str(tmp_path / "run")]) == 2
    assert not (tmp_path / "run").exists()


def test_display_summary_uses_only_display_rows_and_population_std():
    summary = summarize_display_rows([[1.0, 2.0], [3.0, 6.0]])
    assert summary.source == "display_rows"
    assert summary.n_display == 2
    assert summary.mean == (2.0, 4.0)
    assert summary.std == (1.0, 2.0)
    assert summary.minimum == (1.0, 2.0)
    assert summary.maximum == (3.0, 6.0)
    assert summary.correlation == pytest.approx(1.0)
    assert summarize_display_rows([[1.0, 2.0], [1.0, 3.0]]).correlation is None
    with pytest.raises(ValueError):
        summarize_display_rows([])
