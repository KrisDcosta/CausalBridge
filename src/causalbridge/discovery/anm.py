"""Held-out RBF-KRR / biased-HSIC ANM diagnostic with pre-saved original inputs.

This is a bounded pilot method, not causal proof or a benchmark result. NumPy is
an optional dependency imported only AFTER the original request has been saved.
"""

import importlib
import importlib.metadata
import math
import platform
from dataclasses import dataclass
from pathlib import Path

from causalbridge.discovery.anm_requests import (
    SavedANMRequest,
    load_anm_request,
    read_json,
    write_json_exclusive,
)
from causalbridge.discovery.schemas import ANMProvenance, ANMResult, canonical_digest
from causalbridge.verifier.bindings import ANMRequestBinding

LIMITATIONS = (
    "Directional preference under additive-noise assumptions; not causal proof or probability.",
    "Hidden confounding, feedback and independent sampling are not verified.",
    "Fixed holdout and pilot settings; select/freeze threshold on development data only.",
    "Caller supplies selected rows and sampling_seed; original selection is not certified.",
)


class _DiagnosticError(Exception):
    def __init__(self, category: str, code: str):
        self.category, self.code = category, code
        super().__init__(code)


def _numpy():
    try:
        return importlib.import_module("numpy")
    except ImportError as exc:
        raise _DiagnosticError("configuration", "numpy_unavailable") from exc


def _rbf(left, right, gamma):
    np = _numpy()
    return np.exp(-gamma * (left[:, None] - right[None, :]) ** 2)


def _hsic(cause, residual):
    """Biased HSIC = sum(Kc * Lc)/n^2, median-positive-distance RBF kernels."""
    np = _numpy()
    kernels, bandwidths = [], []
    for vector in (cause, residual):
        distances = np.abs(vector[:, None] - vector[None, :])
        positive = distances[np.triu_indices(len(vector), 1)]
        positive = positive[positive > 0]
        if not positive.size:
            raise _DiagnosticError("dependence", "undefined_kernel_bandwidth")
        bandwidth = float(np.median(positive))
        if not math.isfinite(bandwidth) or bandwidth <= 0:
            raise _DiagnosticError("dependence", "undefined_kernel_bandwidth")
        kernel = np.exp(-0.5 * (distances / bandwidth) ** 2)
        centered = kernel - kernel.mean(axis=0) - kernel.mean(axis=1)[:, None] + kernel.mean()
        kernels.append(centered)
        bandwidths.append(bandwidth)
    score = float(np.sum(kernels[0] * kernels[1]) / len(cause) ** 2)
    if not math.isfinite(score):
        raise _DiagnosticError("dependence", "nonfinite_hsic_result")
    return score, bandwidths


def _calculate(saved: SavedANMRequest, record: dict) -> tuple[float, float]:
    config, rows = saved.config, saved.sample.rows
    if len(rows) < config.minimum_rows:
        raise _DiagnosticError("input_validation", "insufficient_rows")
    if len(rows) > config.maximum_rows:
        raise _DiagnosticError("input_validation", "too_many_rows")
    if min(len(saved.training_indices), len(saved.evaluation_indices)) < 2:
        raise _DiagnosticError("input_validation", "insufficient_split_rows")
    if any(len(set(column)) < 3 for column in zip(*rows, strict=True)):
        raise _DiagnosticError("input_validation", "insufficient_variation")
    np = _numpy()
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            data = np.asarray(rows, dtype=np.float64)
            training = data[list(saved.training_indices)]
            evaluation = data[list(saved.evaluation_indices)]
            means, scales = training.mean(axis=0), training.std(axis=0, ddof=0)
            if not np.all(scales > 0):
                raise _DiagnosticError("input_validation", "constant_training_column")
            train = (training - means) / scales
            test = (evaluation - means) / scales
            record["preprocessing"] = {
                "variable_order": ["A", "B"],
                "training_means": means.tolist(),
                "training_population_stds": scales.tolist(),
                "evaluation_transform": "use_training_means_and_scales",
                "residual_scaling": config.residual_scaling,
                "directions": {},
            }
            scores = []
            for name, cause, effect in (("A_to_B", 0, 1), ("B_to_A", 1, 0)):
                kernel = _rbf(train[:, cause], train[:, cause], config.kernel_gamma)
                coefficients = np.linalg.solve(
                    kernel + config.ridge_alpha * np.eye(len(train)), train[:, effect]
                )
                predicted = (
                    _rbf(test[:, cause], train[:, cause], config.kernel_gamma) @ coefficients
                )
                residuals = test[:, effect] - predicted
                residual_mean = float(residuals.mean())
                residual_std = float(residuals.std(ddof=0))
                if residual_std <= 0:
                    raise _DiagnosticError("dependence", "constant_evaluation_residual")
                normalized = (residuals - residual_mean) / residual_std
                try:
                    score, bandwidths = _hsic(test[:, cause], normalized)
                except FloatingPointError as exc:
                    raise _DiagnosticError("dependence", "nonfinite_hsic_result") from exc
                record["preprocessing"]["directions"][name] = {
                    "evaluation_residual_mean": residual_mean,
                    "evaluation_residual_population_std": residual_std,
                    "hsic_cause_bandwidth": bandwidths[0],
                    "hsic_residual_bandwidth": bandwidths[1],
                }
                scores.append(score)
            return tuple(scores)
    except np.linalg.LinAlgError as exc:
        raise _DiagnosticError("regression", "regression_fit_failed") from exc
    except FloatingPointError as exc:
        raise _DiagnosticError("regression", "nonfinite_regression_result") from exc


def execute_anm_request(directory: Path) -> ANMResult:
    """Load/verify the independently saved request, execute once, persist the result.

    Storage/configuration corruption raises before execution. Valid but unusable
    numeric samples produce ANMResult(status='error'). Original files are never
    overwritten. After an interrupted attempt, use a fresh directory, not a retry
    that overwrites the old receipt. result.json is the completion marker.
    """
    saved = load_anm_request(directory)
    for name in ("result.json", "reproducibility.json", "execution_started.json"):
        if (saved.directory / name).exists():
            raise FileExistsError(f"ANM attempt already contains {name}; use a new directory")
    write_json_exclusive(
        saved.directory / "execution_started.json",
        {"request_digest": canonical_digest(saved.request.model_dump(mode="json"))},
    )
    try:
        numpy_version = importlib.metadata.version("numpy")
    except importlib.metadata.PackageNotFoundError:
        numpy_version = None
    record = {
        "record_version": "anm-reproducibility-1.0",
        "request_digest": canonical_digest(saved.request.model_dump(mode="json")),
        "sample_digest": saved.request.sample_digest,
        "config_digest": saved.request.config_digest,
        "config": saved.config.model_dump(mode="json"),
        "training_indices": saved.training_indices,
        "evaluation_indices": saved.evaluation_indices,
        "dependencies": {"python": platform.python_version(), "numpy": numpy_version},
        "preprocessing": None,
    }
    fields = dict(status="ok", threshold=saved.config.threshold)
    try:
        score_ab, score_ba = _calculate(saved, record)
        margin = score_ba - score_ab
        threshold = saved.config.threshold
        decision = (
            None
            if threshold is None
            else "A_to_B"
            if margin > threshold
            else "B_to_A"
            if margin < -threshold
            else "abstain"
        )
        fields.update(
            score_ab=score_ab,
            score_ba=score_ba,
            margin=margin,
            decision=decision,
            predicted_direction=None if decision in (None, "abstain") else decision,
            reason_code="threshold_not_configured"
            if threshold is None
            else "ambiguous_margin"
            if decision == "abstain"
            else None,
        )
    except _DiagnosticError as exc:
        fields.update(status="error", reason_code=exc.code, error_category=exc.category)
    provenance = ANMProvenance(
        **{
            k: getattr(saved.request, k)
            for k in (
                "sample_digest",
                "ab_mapping_id",
                "selected_row_count",
                "training_row_count",
                "evaluation_row_count",
                "sampling_seed",
                "split_seed",
                "config_digest",
                "method_version",
                "configuration_version",
            )
        },
        reproducibility_ref=canonical_digest(record),
        validation_findings=(
            "finite_numeric_pairs_validated",
            "original_request_saved_before_method",
        ),
        input_quality_warnings=("caller_sampling_not_independently_verified",),
    )
    result = ANMResult(**fields, provenance=provenance, limitations=LIMITATIONS)
    write_json_exclusive(saved.directory / "reproducibility.json", record)
    write_json_exclusive(saved.directory / "result.json", result.model_dump(mode="json"))
    return result


@dataclass(frozen=True)
class ANMArtifacts:
    request: ANMRequestBinding
    result: ANMResult
    reproducibility: dict


def load_anm_artifacts(directory: Path) -> ANMArtifacts:
    """Verify durable inputs/result/reproducibility for the runner's separate receipt.

    The request is always read from request.json and actual saved inputs, never
    reconstructed from returned provenance. Digests are consistency checks, not
    signatures or authentication of a trusted artifact store.
    """
    saved = load_anm_request(directory)
    result = ANMResult.model_validate(read_json(saved.directory / "result.json"))
    record = read_json(saved.directory / "reproducibility.json")
    if canonical_digest(record) != result.provenance.reproducibility_ref:
        raise ValueError("ANM reproducibility record digest mismatch")
    if record.get("request_digest") != canonical_digest(saved.request.model_dump(mode="json")):
        raise ValueError("ANM reproducibility request binding mismatch")
    expected = {
        "sample_digest": saved.request.sample_digest,
        "config_digest": saved.request.config_digest,
        "config": saved.config.model_dump(mode="json"),
        "training_indices": list(saved.training_indices),
        "evaluation_indices": list(saved.evaluation_indices),
    }
    if any(record.get(field) != value for field, value in expected.items()):
        raise ValueError("ANM reproducibility inputs do not match original request")
    for field in (
        "sample_digest",
        "ab_mapping_id",
        "selected_row_count",
        "training_row_count",
        "evaluation_row_count",
        "sampling_seed",
        "split_seed",
        "config_digest",
        "method_version",
        "configuration_version",
    ):
        if getattr(saved.request, field) != getattr(result.provenance, field):
            raise ValueError(f"ANM result does not match original request: {field}")
    if saved.request.threshold != result.threshold:
        raise ValueError("ANM result does not match original threshold")
    return ANMArtifacts(saved.request, result, record)
