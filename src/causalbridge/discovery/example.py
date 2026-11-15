"""Generate inspectable contract examples, not a benchmark or computed diagnostic.

Run: python -m causalbridge.discovery.example --output examples/track_b_contract.json
"""

import argparse
import json
from pathlib import Path

from causalbridge.discovery.evidence import build_packages, digest, select_pair
from causalbridge.discovery.prompts import PROMPT_VERSION, output_schema, render
from causalbridge.discovery.contracts import (
    DirectionProposal,
    MethodCard,
    PredictionAttempt,
    ReleaseRecord,
    RuntimePair,
)


def contract_example() -> dict:
    pair = RuntimePair(
        case_id="D0001",
        variables=(
            {"name": "Synthetic input", "unit": "m"},
            {"name": "Synthetic response", "unit": "s"},
        ),
        rows=((1.0, 2.0), (3.0, 6.0), (5.0, 4.0), (7.0, 8.0)),
    )
    selected = select_pair(pair)
    method = MethodCard(
        method_version="scripted-fixture-v1",
        sample_digest=selected.method_sample_digest,
        config_digest=digest({"fixture": True}),
        n_selected=4,
        status="ok",
        score_ab=0.1,
        score_ba=0.3,
        margin=0.2,
        threshold=0.05,
        threshold_version="fixture-only",
        predicted_direction="A_to_B",
        reason_code="scripted_preference",
        limitations=(
            "Scripted contract fixture; no ANM calculation was performed.",
            "Observational evidence cannot rule out hidden confounding or feedback.",
        ),
    )
    packages = build_packages(selected, method)
    proposal = DirectionProposal(
        response_action="answer",
        predicted_direction="A_to_B",
        evidence_refs=("method:anm:v1",),
        method_attribution="A_to_B",
        claim_scope="plausible_direction",
        explanation="Fixture preference, not causal proof.",
    )
    abstention = DirectionProposal(
        **(
            proposal.model_dump()
            | {
                "response_action": "abstain",
                "predicted_direction": None,
                "explanation": "Fixture uncertainty warrants abstention.",
            }
        )
    )
    answer = PredictionAttempt(
        attempt_id="fixture-s1-answer",
        evidence_digest=packages[3].evidence_digest,
        condition="S1",
        status="parsed",
        raw_text=proposal.model_dump_json(),
        proposal=proposal,
        failure_code=None,
        model="scripted-fixture",
        model_mode="scripted_fixture",
    )
    failed = PredictionAttempt(
        **(
            answer.model_dump()
            | {
                "attempt_id": "fixture-s1-failed",
                "status": "parse_error",
                "raw_text": "not JSON",
                "proposal": None,
                "failure_code": "structured_output_error",
            }
        )
    )
    release = ReleaseRecord(
        parent_attempt_id=answer.attempt_id,
        parent_attempt_digest=digest(answer.model_dump()),
        checker_version="scripted-example-only",
        process_status="passed",
        response_action="answer",
        released_direction=proposal.predicted_direction,
        reason_codes=("scripted_pass",),
    )
    return {
        "notice": "Illustrative contracts only: no model, ANM or production checker was run.",
        "prompt_version": PROMPT_VERSION,
        "runtime_input": pair.model_dump(mode="json"),
        "private_selection_do_not_prompt": selected.selection.model_dump(mode="json"),
        "packages": [e.model_dump(mode="json") for e in packages],
        "prompts": {e.payload.package: {c: render(e, c) for c in ("S0", "S1")} for e in packages},
        "output_schema": output_schema(),
        "answer_attempt": answer.model_dump(mode="json"),
        "abstention_proposal": abstention.model_dump(mode="json"),
        "failed_attempt": failed.model_dump(mode="json"),
        "illustrative_release": release.model_dump(mode="json"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract_example(), indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
