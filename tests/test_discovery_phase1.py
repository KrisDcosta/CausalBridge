"""Hand fixtures and adversarial boundaries, without model or teammate dependencies."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from causalbridge.discovery.evidence import (
    build_packages,
    canonical_json,
    digest,
    sample_digest,
    select_pair,
    summarize,
)
from causalbridge.discovery.prompts import BASE, CAUTION, output_schema, render
from causalbridge.discovery.contracts import (
    DirectionProposal,
    EvidencePackage,
    MethodCard,
    RuntimePair,
    SelectionSpec,
)
from causalbridge.llm.parser import parse_json


def pair():
    return RuntimePair(
        case_id="D0001",
        variables=({"name": "Input", "unit": "m"}, {"name": "Output", "unit": "s"}),
        rows=((1.0, 2.0), (3.0, 6.0)),
    )


def card(selected, **changes):
    data = dict(
        method_version="scripted-fixture-v1",
        sample_digest=selected.method_sample_digest,
        config_digest="a" * 64,
        n_selected=len(selected.method_rows),
        status="ok",
        score_ab=0.1,
        score_ba=0.3,
        margin=0.2,
        threshold=0.05,
        threshold_version="fixture-only",
        predicted_direction="A_to_B",
        reason_code="directional_preference",
        limitations=("Scripted, not computed ANM.",),
    )
    return MethodCard(**(data | changes))


def test_hand_calculated_population_summaries():
    a, b = summarize(((1.0, 2.0), (3.0, 6.0)))
    assert a.model_dump() == dict(n=2, minimum=1.0, maximum=3.0, mean=2.0, population_std=1.0)
    assert b.model_dump() == dict(n=2, minimum=2.0, maximum=6.0, mean=4.0, population_std=2.0)


def test_exact_matched_packages_and_prompt_intervention():
    s = select_pair(pair())
    e1, e2, e3, e4 = build_packages(s, card(s))
    assert e1.payload.display_rows == () and e1.payload.summary is None
    assert e2.payload.context is None
    assert e2.payload.display_rows == e3.payload.display_rows == e4.payload.display_rows
    assert e2.payload.summary == e3.payload.summary == e4.payload.summary
    assert e1.payload.context == e3.payload.context == e4.payload.context
    assert e2.display_sample_digest == e3.display_sample_digest == e4.display_sample_digest
    assert len({p.evidence_digest for p in (e1, e2, e3, e4)}) == 4
    for e in (e1, e2, e3, e4):
        s0, s1 = render(e, "S0"), render(e, "S1")
        assert s0[1] == s1[1]
        assert s0[0]["content"] == BASE
        assert s1[0]["content"] == BASE + CAUTION
        assert "selection" not in s0[1]["content"]
    assert "method_sample_digest" not in render(e3, "S0")[1]["content"]
    with pytest.raises(ValueError):
        render(e4, "S2")


def test_sampling_reproducibility_subset_and_mapping():
    raw = pair().model_dump() | {"rows": [(float(i), float(i + 100)) for i in range(400)]}
    p = RuntimePair(**raw)
    a = select_pair(p)
    assert a == select_pair(p)
    assert len(a.method_rows) == 256 and len(a.display_rows) == 64
    assert set(a.selection.display_indices) <= set(a.selection.method_indices)
    assert tuple(sorted(a.selection.method_indices)) == a.selection.method_indices
    assert a.variables == tuple(p.variables[i] for i in a.selection.column_order)
    for original, row in zip(a.selection.display_indices, a.display_rows, strict=True):
        assert row == tuple(p.rows[original][i] for i in a.selection.column_order)
    orders = {
        select_pair(p, SelectionSpec(mapping_seed=i)).selection.column_order for i in range(20)
    }
    assert orders == {(0, 1), (1, 0)}
    assert select_pair(p, SelectionSpec(sample_seed=999)).method_rows != a.method_rows


@pytest.mark.parametrize(
    "row",
    [(True, 1.0), ("2", 1.0), (float("nan"), 1.0), (float("inf"), 1.0), (1.0,), (1.0, 2.0, 3.0)],
)
def test_invalid_numeric_rows_rejected(row):
    with pytest.raises(ValidationError):
        RuntimePair(**(pair().model_dump() | {"rows": [row]}))


def test_oracle_fields_rejected_and_no_private_provenance_in_prompts():
    with pytest.raises(ValidationError):
        RuntimePair(**(pair().model_dump() | {"gold_direction": "GOLD-SENTINEL"}))
    s = select_pair(pair())
    for e in build_packages(s, card(s)):
        public = json.dumps(render(e, "S0"))
        assert s.selection.source_digest not in public
        assert "column_order" not in public and "method_indices" not in public
        assert "gold_direction" not in public


def test_hash_golden_vector_signed_zero_and_method_binding():
    assert canonical_json({"z": -0.0, "a": [1.0, 2.0]}) == '{"a":[1.0,2.0],"z":0.0}'
    expected = hashlib.sha256(b'{"a":[1.0,2.0],"z":0.0}').hexdigest()
    assert digest({"z": -0.0, "a": [1.0, 2.0]}) == expected
    assert sample_digest(((1.0, 2.0),)) != sample_digest(((2.0, 1.0),))
    s = select_pair(pair())
    with pytest.raises(ValueError, match="different method sample"):
        build_packages(s, card(s, sample_digest="b" * 64))
    with pytest.raises(ValueError, match="count mismatch"):
        build_packages(s, card(s, n_selected=99))
    e = build_packages(s, card(s))[0]
    with pytest.raises(ValueError, match="digest mismatch"):
        render(e.model_copy(update={"evidence_digest": "b" * 64}), "S0")


@pytest.mark.parametrize(
    "changes",
    [
        {"margin": 0.9},
        {"predicted_direction": "B_to_A"},
        {"threshold": None},
        {"threshold_version": None},
        {"score_ab": None},
        {"status": "error"},
        {"threshold": -1.0},
    ],
)
def test_inconsistent_method_result_rejected(changes):
    with pytest.raises(ValidationError):
        card(select_pair(pair()), **changes)


def test_method_ambiguity_failure_and_missing_threshold_are_retained():
    s = select_pair(pair())
    controls = [
        card(s, threshold=0.2, predicted_direction=None, reason_code="ambiguous"),
        card(
            s,
            threshold=None,
            threshold_version=None,
            predicted_direction=None,
            reason_code="threshold_not_configured",
        ),
        card(
            s,
            status="error",
            score_ab=None,
            score_ba=None,
            margin=None,
            threshold=None,
            threshold_version=None,
            predicted_direction=None,
            reason_code="constant_column",
        ),
    ]
    for m in controls:
        assert build_packages(s, m)[3].payload.method == m


def test_package_registry_rejects_unavailable_evidence():
    s = select_pair(pair())
    e = build_packages(s, card(s))[0].payload.model_dump()
    with pytest.raises(ValidationError):
        EvidencePackage(**(e | {"evidence_ids": ["rows:r0001"]}))
    with pytest.raises(ValidationError):
        EvidencePackage(**(e | {"method": card(s)}))


def test_direction_proposals_and_strict_parser():
    data = dict(
        response_action="answer",
        predicted_direction="A_to_B",
        evidence_refs=["summary:A"],
        method_attribution=None,
        claim_scope="plausible_direction",
        explanation="A qualified preference.",
    )
    assert parse_json(json.dumps(data), DirectionProposal).predicted_direction == "A_to_B"
    assert parse_json(
        json.dumps(data | {"response_action": "abstain", "predicted_direction": None}),
        DirectionProposal,
    )
    for change in (
        {"predicted_direction": None},
        {"gold_direction": "A_to_B"},
        {"predicted_direction": "positive"},
    ):
        with pytest.raises(ValidationError):
            parse_json(json.dumps(data | change), DirectionProposal)
    with pytest.raises(ValueError):
        parse_json('{"response_action":"answer","response_action":"abstain"}', DirectionProposal)
    assert output_schema()["additionalProperties"] is False


def test_contract_example_roundtrip_and_no_execution():
    from causalbridge.discovery.example import contract_example
    from causalbridge.discovery.contracts import PredictionAttempt, ReleaseRecord

    example = contract_example()
    answer = PredictionAttempt.model_validate(example["answer_attempt"])
    failed = PredictionAttempt.model_validate(example["failed_attempt"])
    release = ReleaseRecord.model_validate(example["illustrative_release"])
    assert failed.raw_text == "not JSON" and failed.proposal is None
    assert answer.input_tokens is None and answer.model_mode == "scripted_fixture"
    assert release.parent_attempt_digest == digest(answer.model_dump())
    assert release.released_direction == answer.proposal.predicted_direction
    for change in (
        {"response_action": "answer", "predicted_direction": None},
        {"response_action": "abstain", "predicted_direction": "A_to_B"},
    ):
        with pytest.raises(ValidationError):
            DirectionProposal(**(answer.proposal.model_dump() | change))
    with pytest.raises(ValidationError):
        PredictionAttempt(**(failed.model_dump() | {"raw_text": None}))
    with pytest.raises(ValidationError):
        ReleaseRecord(**(release.model_dump() | {"process_status": "rejected"}))
    assert len(example["packages"]) == 4
    assert sum(len(p) for p in example["prompts"].values()) == 8


def test_constant_columns_preserved_and_selection_corruption_rejected():
    p = RuntimePair(**(pair().model_dump() | {"rows": [(1.0, 2.0), (1.0, 2.0)]}))
    s = select_pair(p)
    method = card(
        s,
        status="error",
        score_ab=None,
        score_ba=None,
        margin=None,
        predicted_direction=None,
        threshold=None,
        threshold_version=None,
        reason_code="constant_column",
    )
    assert build_packages(s, method)[3].payload.summary[0].population_std == 0.0
    corrupted = s.model_copy(update={"display_sample_digest": "c" * 64})
    with pytest.raises(ValueError, match="display sample digest"):
        build_packages(corrupted, method)
