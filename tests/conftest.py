import pytest

from causalbridge.schemas import Assumptions, Query, RuntimeCase


@pytest.fixture
def assumptions():
    return Assumptions(
        correct_dag=True, fully_observed=True, independent_noise=True, positivity=True
    )


@pytest.fixture
def toy(assumptions):
    return RuntimeCase.model_validate(
        dict(
            case_id="toy",
            graph_nodes=["X", "Y"],
            graph_edges=[["X", "Y"]],
            question="Does increasing X increase Y?",
            assumptions=assumptions,
            visible_cpts=[
                {"node": "X", "p_one": {"": 0.5}},
                {"node": "Y", "parents": ["X"], "p_one": {"0": 0.3, "1": 0.7}},
            ],
        )
    )


@pytest.fixture
def query():
    return Query(cause="X", outcome="Y", question_type="effect_direction")


@pytest.fixture
def bound_direction():
    """Trusted offline cache fixture; request values precede tested corruptions."""
    import json
    from pathlib import Path

    from causalbridge.discovery.schemas import (
        DirectionEvidence,
        DirectionPrediction,
        canonical_digest,
    )
    from causalbridge.verifier.bindings import ANMRequestBinding, VerificationContext

    records = [
        json.loads(line)
        for line in (Path(__file__).parents[1] / "examples/track_b_phase1.jsonl")
        .read_text()
        .splitlines()
    ]

    def make(index=3, *, claims=None, direction="A_to_B", abstained=False):
        original = records[index]
        e = DirectionEvidence.model_validate(original["input"])
        payload = original["prediction"] | dict(
            predicted_direction=direction,
            abstained=abstained,
            reason_code="model_abstention" if abstained else None,
        )
        if claims is not None:
            payload["claims"] = claims
        p = DirectionPrediction.model_validate(payload)
        # In this fixture the previously saved request is read from fixed mock
        # inputs, not from a result supplied to the verifier under test.
        request = None
        if e.package == "E4":
            request = ANMRequestBinding(
                case_id="D0042",
                ab_mapping_id="mapping-001",
                sample_digest="sha256:a6f990434ce15fe3de7f982f31c954671b9a276c38a018b32a4b235168607f77",
                config_digest=canonical_digest(original["mock_reproducibility_record"]["config"]),
                method_version="mock-not-anm",
                configuration_version="mock-dev-1",
                selected_row_count=4,
                training_row_count=3,
                evaluation_row_count=1,
                sampling_seed=261,
                split_seed=261,
                threshold=original["mock_reproducibility_record"]["config"]["threshold"],
            )
        context = VerificationContext(
            case_id=e.case_id,
            package_digest=e.package_digest,
            proposal_digest=p.proposal_digest,
            ab_mapping_id=e.ab_mapping_id,
            mapping_seed=e.mapping_seed,
            display_sample_digest=e.display_sample_digest,
            method_result_digest=None
            if e.method_result is None
            else canonical_digest(e.method_result.model_dump(mode="json")),
            method_request=request,
        )
        return e, p, context

    return make
