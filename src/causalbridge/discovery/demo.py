"""Offline API examples, not evidence packaging or an experiment runner.

Run: uv run python -m causalbridge.discovery.demo > /tmp/track-b-demo.jsonl
All scores, data and replies are scripted; no scientific performance claims.
"""

import json
from collections.abc import Iterator

from causalbridge.discovery.schemas import (
    ANMProvenance,
    ANMResult,
    DirectionEvidence,
    DirectionPrediction,
    PromptCondition,
    canonical_digest,
)
from causalbridge.llm.client import Generation
from causalbridge.llm.predictor import predict_direction
from causalbridge.verifier.checks import check_prediction


class ScriptedDirectionModel:
    """Injected JSONModel implementation, deliberately offline."""

    def __init__(self, prediction: DirectionPrediction):
        self.prediction = prediction

    def generate(self, messages: list[dict[str, str]], schema: dict) -> Generation:
        return Generation(text=self.prediction.model_dump_json(), model="scripted-not-an-llm")


def demo_records() -> Iterator[dict]:
    """Emit E1–E4, then ambiguous, unconfigured and failed ANM examples."""
    rows = ((205.0, 9.7), (46.0, 8.2))
    method_rows = (*rows, (100.0, 8.8), (80.0, 8.5))
    # This linked record illustrates the required contents. A real adapter must
    # persist and verify it and retain its training-derived numerical settings.
    config = dict(
        regression="mock",
        kernel="mock",
        hyperparameters={},
        hsic_estimator="mock",
        bandwidth_rule="mock",
        threshold=0.01,
        score_convention="lower residual dependence favors direction",
    )
    repro = dict(
        transforms=["identity", "identity"],
        training_means=[0.0, 0.0],
        training_scales=[1.0, 1.0],
        residual_scaling="none",
        evaluation_transform="none",
        config=config,
        threshold_version="mock-dev-1",
    )
    provenance = ANMProvenance(
        sample_digest=canonical_digest(dict(ab_mapping_id="mapping-001", rows=method_rows)),
        ab_mapping_id="mapping-001",
        selected_row_count=4,
        training_row_count=3,
        evaluation_row_count=1,
        sampling_seed=261,
        split_seed=261,
        config_digest=canonical_digest(config),
        method_version="mock-not-anm",
        configuration_version="mock-dev-1",
        reproducibility_ref=canonical_digest(repro),
        validation_findings=(),
        input_quality_warnings=("Scripted fixture, not real ANM",),
    )
    base = dict(
        status="ok",
        score_ab=0.012,
        score_ba=0.035,
        margin=0.023,
        threshold=0.01,
        decision="A_to_B",
        predicted_direction="A_to_B",
        reason_code=None,
        provenance=provenance,
        limitations=("ANM assumptions are unverified; confounding/feedback are possible.",),
    )
    states = [
        ("E1", None),
        ("E2", None),
        ("E3", None),
        ("E4", ANMResult(**base)),
        (
            "E4",
            ANMResult(
                **(
                    base
                    | dict(
                        score_ba=0.012,
                        margin=0.0,
                        decision="abstain",
                        predicted_direction=None,
                        reason_code="ambiguous_margin",
                    )
                )
            ),
        ),
        (
            "E4",
            ANMResult(
                **(
                    base
                    | dict(
                        threshold=None,
                        decision=None,
                        predicted_direction=None,
                        reason_code="threshold_not_configured",
                    )
                )
            ),
        ),
        (
            "E4",
            ANMResult(
                **(
                    base
                    | dict(
                        status="error",
                        score_ab=None,
                        score_ba=None,
                        margin=None,
                        decision=None,
                        predicted_direction=None,
                        reason_code="mock_fit_failure",
                        error_category="regression",
                    )
                )
            ),
        ),
    ]
    condition = PromptCondition(
        condition_id="offline-example",
        version="1",
        instructions="Make a cautious prediction from supplied evidence.",
    )
    for package, method in states:
        method_repro = None
        if method is not None:
            method_config = config | {"threshold": method.threshold}
            method_repro = repro | {"config": method_config}
            data = method.model_dump(mode="json")
            data["provenance"].update(
                config_digest=canonical_digest(method_config),
                reproducibility_ref=canonical_digest(method_repro),
            )
            method = ANMResult.model_validate(data)
        payload = dict(
            case_id="D0042", package=package, ab_mapping_id="mapping-001", mapping_seed=261
        )
        if package != "E2":
            payload.update(variable_labels=("Altitude", "Temperature"), units=("m", "C"))
        if package != "E1":
            payload.update(
                display_rows=rows,
                display_sampling_seed=261,
                summary=dict(n_display=2, mean=(125.5, 8.95)),
            )
        if method is not None:
            payload["method_result"] = method
        evidence = DirectionEvidence.model_validate(payload)
        direction = "A_to_B" if method is None else method.predicted_direction
        claims = (
            []
            if method is None or method.decision is None
            else [dict(type="method_direction", evidence_ref="method_result", direction=direction)]
        )
        proposal = DirectionPrediction(
            case_id=evidence.case_id,
            package_digest=evidence.package_digest,
            predicted_direction=direction,
            abstained=direction is None,
            reason_code="scripted_abstention" if direction is None else None,
            claims=claims,
        )
        execution = predict_direction(evidence, condition, ScriptedDirectionModel(proposal))
        yield dict(
            fixture_only=True,
            input=evidence.model_dump(mode="json"),
            display_sample_digest=evidence.display_sample_digest,
            package_digest=evidence.package_digest,
            execution=execution.model_dump(mode="json"),
            check=check_prediction(evidence, proposal).model_dump(mode="json"),
            mock_reproducibility_record=method_repro,
        )


if __name__ == "__main__":
    for record in demo_records():
        print(json.dumps(record, ensure_ascii=True, allow_nan=False))
