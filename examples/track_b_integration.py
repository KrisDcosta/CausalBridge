"""Offline API smoke example. Replays fixed fixtures, not an experiment runner.

uv run python examples/track_b_integration.py > /tmp/track-b-integration.jsonl
Each line saves complete S0/S1 executions and the cached S1-to-S2 decision.
All observations, scores and model replies are scripted; no accuracy claims.
"""

import json
from pathlib import Path

from causalbridge.discovery.schemas import (
    DirectionEvidence,
    PromptCondition,
    canonical_digest,
)
from causalbridge.llm.client import Generation
from causalbridge.llm.predictor import PredictionExecution, predict_direction
from causalbridge.verifier.bindings import ANMRequestBinding, VerificationContext
from causalbridge.verifier.checks import check_prediction


class FixtureModel:
    """JSONModel transport with a fixed reply and observable call count."""

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def generate(self, messages, schema):
        self.calls += 1
        return Generation(text=self.reply, model="scripted-offline")


def original_request(record):
    """Mock original inputs, independent of returned ANMResult fields.

    Anish must save this from his actual request before executing the method.
    This example uses the same declared mock inputs as discovery/demo.py.
    """
    method_rows = [[205.0, 9.7], [46.0, 8.2], [100.0, 8.8], [80.0, 8.5]]
    config = record["mock_reproducibility_record"]["config"]
    return ANMRequestBinding(
        case_id="D0042",
        ab_mapping_id="mapping-001",
        sample_digest=canonical_digest(dict(ab_mapping_id="mapping-001", rows=method_rows)),
        config_digest=canonical_digest(config),
        selected_row_count=len(method_rows),
        training_row_count=3,
        evaluation_row_count=1,
        sampling_seed=261,
        split_seed=261,
        threshold=config["threshold"],
        method_version="mock-not-anm",
        configuration_version="mock-dev-1",
    )


def integration_records():
    folder = Path(__file__).parent
    phase1 = [
        json.loads(line) for line in (folder / "track_b_phase1.jsonl").read_text().splitlines()
    ]
    phase2 = [
        json.loads(line) for line in (folder / "track_b_phase2.jsonl").read_text().splitlines()
    ]
    names = ["E1", "E2", "E3", "E4", "E4_ambiguous", "E4_unconfigured", "E4_error"]
    cases = [
        (name, r["input"], r["prediction"], None, r) for name, r in zip(names, phase1, strict=True)
    ]
    cases += [(r["name"], r["evidence"], r["saved_prediction"], r["context"], None) for r in phase2]
    # Example prompt selection is outside predict_direction. Kris supplies the
    # actual frozen S0/S1 instructions, versions and condition IDs.
    conditions = [
        PromptCondition(condition_id=c, version="offline-1", instructions=text)
        for c, text in [
            ("S0", "Predict using the supplied evidence."),
            ("S1", "Predict cautiously using the supplied evidence."),
        ]
    ]
    for name, raw_evidence, reply, cached_context, original in cases:
        evidence = DirectionEvidence.model_validate(raw_evidence)
        # Freeze original evidence identities BEFORE generation. This receipt
        # comes from the exact evidence shown, not a later candidate for checking.
        receipt = dict(
            case_id=evidence.case_id,
            package_digest=evidence.package_digest,
            ab_mapping_id=evidence.ab_mapping_id,
            mapping_seed=evidence.mapping_seed,
            display_sample_digest=evidence.display_sample_digest,
            method_result_digest=None
            if evidence.method_result is None
            else canonical_digest(evidence.method_result.model_dump(mode="json")),
            method_request=None
            if evidence.method_result is None or original is None
            else original_request(original).model_dump(mode="json"),
        )
        # Existing Phase 2 receipts were independently saved with those fixtures.
        # Preserve them, including the deliberately missing original request.
        receipt_json = json.dumps(cached_context if cached_context is not None else receipt)
        model = FixtureModel(json.dumps(reply))
        executions = []
        for condition in conditions:
            trace = predict_direction(evidence, condition, model)
            # JSON round-trip stands in for runner persistence/retrieval. Save
            # the ENTIRE trace, even generation/parsing/binding failures.
            executions.append(PredictionExecution.model_validate_json(trace.model_dump_json()))
        s0, s1 = executions
        record = dict(
            name=name,
            fixture_only=True,
            S0=s0.model_dump(mode="json"),
            S1=s1.model_dump(mode="json"),
            context=None,
            S2=None,
            s2_source_run_id=None,
            s2_skip_reason=None,
        )
        if s1.failure_stage is not None:
            record["s2_skip_reason"] = "prediction_failure"
        else:
            saved = json.loads(receipt_json)
            if cached_context is None:
                # Persist the parsed S1 digest on first successful save. Never
                # replace it from a candidate proposal when retrieving the cache.
                saved["proposal_digest"] = s1.prediction.proposal_digest
            context_json = VerificationContext.model_validate(saved).model_dump_json()
            context = VerificationContext.model_validate_json(context_json)
            check = check_prediction(s1.evidence, s1.prediction, context=context)
            record.update(
                context=context.model_dump(mode="json"),
                S2=check.model_dump(mode="json"),
                s2_source_run_id=s1.run_id,
            )
        record["model_calls"] = model.calls
        yield record


if __name__ == "__main__":
    for record in integration_records():
        print(json.dumps(record, sort_keys=True, allow_nan=False))
