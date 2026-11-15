"""Offline Phase 2 reproduction: 24 fixture calls and zero-call S2 replay.

Run with --output runs/kris-phase2. Repeating reuses saved attempts.
No model inference, ANM computation, production checking or scoring occurs.
"""

import argparse
import json
from pathlib import Path

from causalbridge.discovery.contracts import (
    DirectionProposal,
    MethodCard,
    ReleaseRecord,
    RuntimePair,
)
from causalbridge.discovery.evidence import build_packages, select_pair
from causalbridge.discovery.example import contract_example
from causalbridge.evaluation.runner import ExperimentRunner
from causalbridge.llm.client import Generation


class ScriptedTransport:
    def generate(self, messages, schema):
        payload = json.loads(messages[1]["content"])
        abstain = payload["package"] == "E1"
        proposal = DirectionProposal(
            response_action="abstain" if abstain else "answer",
            predicted_direction=None if abstain else "A_to_B",
            evidence_refs=(),
            method_attribution=None,
            claim_scope="plausible_direction",
            explanation="Scripted fixture only; not a measured research outcome.",
        )
        return Generation(text=proposal.model_dump_json(), model="scripted-fixture")


class ScriptedChecker:
    """Deliberate test double, NOT Vaishak's process checker."""

    version = "scripted-phase2-v1"

    def check(self, envelope, saved, receipt):
        return ReleaseRecord(
            parent_attempt_id=saved.attempt_id,
            parent_attempt_digest=receipt["parent_attempt_digest"],
            checker_version=self.version,
            process_status="passed",
            response_action=saved.proposal.response_action,
            released_direction=saved.proposal.predicted_direction,
            reason_codes=("scripted_fixture_only",),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    example = contract_example()
    packages = []
    for i in range(3):
        pair = RuntimePair.model_validate(example["runtime_input"] | {"case_id": f"D{i + 1:04d}"})
        selected = select_pair(pair)
        method = MethodCard.model_validate(
            example["packages"][3]["payload"]["method"]
            | {"sample_digest": selected.method_sample_digest}
        )
        packages.extend(build_packages(selected, method))
    runner = ExperimentRunner(
        args.output, model_identity="scripted-phase2-v1", identity_verified=True
    )
    result = runner.run(packages, ScriptedTransport())
    releases = runner.replay_s2(result["manifest_id"], ScriptedChecker())
    print(
        json.dumps(
            {
                "notice": "Scripted integration fixtures only",
                "output": str(args.output),
                "manifest_id": result["manifest_id"],
                "new_model_calls": result["new_model_calls"],
                "cached_or_recovered_trials": result["cached_or_recovered_trials"],
                "saved_s1_releases": len(releases),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
