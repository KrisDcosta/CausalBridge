"""Computed ANM + saved original request + existing predictor/checker, on synthetic rows.

uv run --extra anm python examples/anm_integration.py --output runs/anm-handshake
The numerical diagnostic is real. S1 is scripted, not an LLM experiment or a
Tuebingen benchmark. This example does not replace Kris's runner or Faizah's loader.
"""

import argparse
from pathlib import Path
from random import Random

from causalbridge.discovery.anm import execute_anm_request, load_anm_artifacts
from causalbridge.discovery.anm_requests import ANMConfig, save_anm_request, write_json_exclusive
from causalbridge.discovery.demo import ScriptedDirectionModel
from causalbridge.discovery.schemas import (
    DirectionEvidence,
    DirectionPrediction,
    MethodDirectionClaim,
    PromptCondition,
    canonical_digest,
)
from causalbridge.discovery.statistics import summarize_display_rows
from causalbridge.llm.predictor import predict_direction
from causalbridge.verifier.bindings import VerificationContext
from causalbridge.verifier.checks import check_prediction


def run_handshake(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    rng = Random(261)
    rows = []
    for _ in range(256):
        a = rng.uniform(-2, 2)
        rows.append([a, a**3 + rng.gauss(0, 0.2)])
    method_directory = output / "anm"
    # The original receipt is independently persisted BEFORE fitting. This
    # synthetic-only zero threshold is not a development-calibrated choice.
    save_anm_request(
        rows,
        case_id="synthetic-001",
        ab_mapping_id="opaque-map-001",
        directory=method_directory,
        config=ANMConfig(
            threshold=0.0,
            configuration_version="synthetic-smoke-1",
            threshold_selection_version="smoke-zero-not-calibrated",
        ),
    )
    execute_anm_request(method_directory)
    artifacts = load_anm_artifacts(method_directory)
    if artifacts.result.status != "ok":
        raise RuntimeError("Synthetic ANM calculation failed; inspect saved result.json")
    displayed = rows[:32]
    evidence = DirectionEvidence(
        case_id=artifacts.request.case_id,
        package="E4",
        ab_mapping_id=artifacts.request.ab_mapping_id,
        mapping_seed=261,
        variable_labels=("Synthetic measurement A", "Synthetic measurement B"),
        display_rows=displayed,
        display_sampling_seed=261,
        summary=summarize_display_rows(displayed),
        method_result=artifacts.result,
    )
    # Freeze receipt identities before prediction. The expected request is from
    # request.json, NEVER constructed by selecting fields from the ANM result.
    original_receipt = dict(
        case_id=evidence.case_id,
        package_digest=evidence.package_digest,
        ab_mapping_id=evidence.ab_mapping_id,
        mapping_seed=evidence.mapping_seed,
        display_sample_digest=evidence.display_sample_digest,
        method_result_digest=canonical_digest(artifacts.result.model_dump(mode="json")),
        method_request=artifacts.request.model_dump(mode="json"),
    )
    write_json_exclusive(output / "evidence_receipt.json", original_receipt)
    direction = artifacts.result.predicted_direction
    scripted = DirectionPrediction(
        case_id=evidence.case_id,
        package_digest=evidence.package_digest,
        predicted_direction=direction,
        abstained=direction is None,
        reason_code="synthetic_method_ambiguous" if direction is None else None,
        claims=(
            MethodDirectionClaim(
                type="method_direction",
                evidence_ref="method_result",
                direction=direction,
            ),
        ),
    )
    trace = predict_direction(
        evidence,
        PromptCondition(
            condition_id="S1",
            version="scripted-smoke-1",
            instructions="Use the supplied evidence; a prediction is not causal proof.",
        ),
        ScriptedDirectionModel(scripted),
    )
    write_json_exclusive(output / "S1.json", trace.model_dump(mode="json"))
    if trace.failure_stage is not None:
        raise RuntimeError("Scripted predictor failed; inspect S1.json")
    context = VerificationContext(
        **original_receipt,
        proposal_digest=trace.prediction.proposal_digest,
    )
    write_json_exclusive(output / "verification_context.json", context.model_dump(mode="json"))
    # S2 only checks saved artifacts; no new ANM or model call.
    check = check_prediction(trace.evidence, trace.prediction, context=context)
    write_json_exclusive(output / "S2.json", check.model_dump(mode="json"))
    return {
        "synthetic_only": True,
        "scripted_model_only": True,
        "original_request": str(method_directory / "request.json"),
        "anm_status": artifacts.result.status,
        "score_ab": artifacts.result.score_ab,
        "score_ba": artifacts.result.score_ba,
        "margin": artifacts.result.margin,
        "checker_status": check.status,
        "release": check.release,
        "s1_run_id": trace.run_id,
    }


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_handshake(args.output), sort_keys=True))
