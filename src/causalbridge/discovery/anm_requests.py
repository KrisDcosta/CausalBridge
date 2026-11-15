"""Pre-execution ANM inputs and independently persisted verifier receipts.

Only ordered numeric A/B rows and opaque IDs enter this API. No evaluator records
or returned ANMResult are accepted when constructing the original request.
"""

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from causalbridge.discovery.schemas import (
    Digest,
    Identifier,
    Nonnegative,
    Seed,
    canonical_digest,
)
from causalbridge.llm.parser import reject_duplicate_keys
from causalbridge.schemas import Number, Record
from causalbridge.verifier.bindings import ANMRequestBinding

METHOD_VERSION = "anm-krr-hsic-1.0"
Rows = tuple[tuple[Number, Number], ...]
_ROW_ADAPTER = TypeAdapter(Rows)


class ANMConfig(Record):
    """Explicit pilot settings; threshold=None does not release a direction."""

    method_version: Literal["anm-krr-hsic-1.0"] = METHOD_VERSION
    configuration_version: Identifier = "pilot-1"
    threshold: Nonnegative | None = None
    threshold_selection_version: Identifier = "not-calibrated"
    sampling_seed: Seed = 261
    split_seed: Seed = 261
    sample_selection: Literal["caller_selected_without_reordering"] = (
        "caller_selected_without_reordering"
    )
    training_fraction: Annotated[float, Field(strict=True, gt=0, lt=1)] = 0.5
    minimum_rows: Annotated[int, Field(strict=True, ge=8)] = 100
    maximum_rows: Annotated[int, Field(strict=True, ge=8, le=2048)] = 256
    regression: Literal["rbf_kernel_ridge"] = "rbf_kernel_ridge"
    kernel_gamma: Annotated[float, Field(strict=True, gt=0)] = 1.0
    ridge_alpha: Annotated[float, Field(strict=True, gt=0)] = 0.1
    standardization: Literal["training_mean_population_std"] = "training_mean_population_std"
    residual_scaling: Literal["evaluation_mean_population_std"] = "evaluation_mean_population_std"
    hsic_estimator: Literal["biased_centered_rbf"] = "biased_centered_rbf"
    hsic_bandwidth: Literal["median_positive_euclidean_distance"] = (
        "median_positive_euclidean_distance"
    )
    score_convention: Literal["lower_dependence_favored; margin=score_ba-score_ab"] = (
        "lower_dependence_favored; margin=score_ba-score_ab"
    )

    @model_validator(mode="after")
    def validate_limits(self):
        if self.minimum_rows > self.maximum_rows:
            raise ValueError("minimum_rows cannot exceed maximum_rows")
        return self


class ANMSample(Record):
    ab_mapping_id: Identifier
    rows: Rows


class InputManifest(Record):
    schema_version: Literal["anm-inputs-1.0"] = "anm-inputs-1.0"
    request_digest: Digest
    sample_digest: Digest
    config_digest: Digest
    split_digest: Digest


@dataclass(frozen=True)
class SavedANMRequest:
    """Original inputs loaded without reading a method result."""

    directory: Path
    request: ANMRequestBinding
    sample: ANMSample
    config: ANMConfig
    training_indices: tuple[int, ...]
    evaluation_indices: tuple[int, ...]


def validate_rows(rows: object) -> Rows:
    """Normalize finite numeric pairs; reject booleans, ragged and nonnumeric rows."""
    return _ROW_ADAPTER.validate_python(rows)


def write_json_exclusive(path: Path, payload: object) -> None:
    """Flush an exclusive new JSON file before returning. Never overwrite originals."""
    data = (
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    # Persist the directory entry as well as the file contents on local filesystems.
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def _prepare(
    case_id: str, sample: ANMSample, config: ANMConfig, directory: Path
) -> SavedANMRequest:
    indices = list(range(len(sample.rows)))
    Random(config.split_seed).shuffle(indices)
    count = math.floor(len(indices) * config.training_fraction)
    training, evaluation = tuple(indices[:count]), tuple(indices[count:])
    request = ANMRequestBinding(
        case_id=case_id,
        ab_mapping_id=sample.ab_mapping_id,
        sample_digest=canonical_digest(sample.model_dump(mode="json")),
        config_digest=canonical_digest(config.model_dump(mode="json")),
        selected_row_count=len(indices),
        training_row_count=len(training),
        evaluation_row_count=len(evaluation),
        sampling_seed=config.sampling_seed,
        split_seed=config.split_seed,
        threshold=config.threshold,
        method_version=config.method_version,
        configuration_version=config.configuration_version,
    )
    return SavedANMRequest(directory, request, sample, config, training, evaluation)


def _manifest(saved: SavedANMRequest) -> InputManifest:
    return InputManifest(
        request_digest=canonical_digest(saved.request.model_dump(mode="json")),
        sample_digest=saved.request.sample_digest,
        config_digest=saved.request.config_digest,
        split_digest=canonical_digest(
            {
                "training_indices": saved.training_indices,
                "evaluation_indices": saved.evaluation_indices,
            }
        ),
    )


def save_anm_request(
    rows: object,
    *,
    case_id: str,
    ab_mapping_id: str,
    directory: Path,
    config: ANMConfig | None = None,
) -> ANMRequestBinding:
    """Save actual inputs and request BEFORE regression; return Vaishak's exact type.

    Rows are already selected/ordered by the caller. sampling_seed describes that
    caller's selection and cannot certify its honesty. Invalid transport/config
    raises before persistence; valid but unusable samples get saved and later
    yield typed input_validation errors. Use a fresh directory for every attempt.
    """
    sample = ANMSample(ab_mapping_id=ab_mapping_id, rows=validate_rows(rows))
    configuration = ANMConfig.model_validate((config or ANMConfig()).model_dump())
    saved = _prepare(case_id, sample, configuration, Path(directory))
    saved.directory.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(saved.directory / "sample.json", sample.model_dump(mode="json"))
    write_json_exclusive(saved.directory / "config.json", configuration.model_dump(mode="json"))
    write_json_exclusive(saved.directory / "request.json", saved.request.model_dump(mode="json"))
    write_json_exclusive(saved.directory / "inputs.json", _manifest(saved).model_dump(mode="json"))
    return saved.request


def load_anm_request(directory: Path) -> SavedANMRequest:
    """Verify the original request against its actual saved inputs, without any result."""
    directory = Path(directory)
    sample = ANMSample.model_validate(read_json(directory / "sample.json"))
    config = ANMConfig.model_validate(read_json(directory / "config.json"))
    request = ANMRequestBinding.model_validate(read_json(directory / "request.json"))
    original = _prepare(request.case_id, sample, config, directory)
    if original.request != request:
        raise ValueError("Original ANM request does not match saved sample/configuration")
    manifest = InputManifest.model_validate(read_json(directory / "inputs.json"))
    if manifest != _manifest(original):
        raise ValueError("Original ANM input manifest mismatch")
    return original
