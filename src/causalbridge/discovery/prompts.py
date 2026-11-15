"""Exact v1 prompts; no inference, retries, checker or evaluator access."""

from typing import Literal

from causalbridge.discovery.evidence import canonical_json, digest
from causalbridge.discovery.contracts import DirectionProposal, EvidenceEnvelope

PROMPT_VERSION = "direction-v1"
BASE = (
    "Assess which direction is more plausible between A and B using the supplied evidence. "
    "Return one JSON object matching the supplied schema. You may answer A_to_B or B_to_A, "
    "or abstain with a null direction. Cite evidence using only IDs in evidence_ids. "
    "method_attribution describes the diagnostic's direction, abstain, or unavailable; "
    "use null if you do not discuss it. claim_scope describes your claim, not correctness. "
    "These observational inputs and any ANM diagnostic do not establish causal proof. "
    "Unknown confounding and feedback may remain. Give a short explanation."
)
CAUTION = (
    "\nCarefully distinguish observed patterns, background knowledge and method evidence. "
    "Do not invent evidence or overstate what it establishes. Explicitly acknowledge "
    "material uncertainty and abstain when you cannot support a directional preference."
)


def render(envelope: EvidenceEnvelope, condition: Literal["S0", "S1"]) -> list[dict[str, str]]:
    if condition not in {"S0", "S1"}:
        raise ValueError("Only S0/S1 render model prompts; S2 is saved-output checking")
    payload = envelope.payload.model_dump(mode="json", exclude_none=True)
    if digest(payload) != envelope.evidence_digest:
        raise ValueError("Public evidence digest mismatch")
    return [
        {"role": "system", "content": BASE + (CAUTION if condition == "S1" else "")},
        {"role": "user", "content": canonical_json(payload)},
    ]


def output_schema() -> dict:
    return DirectionProposal.model_json_schema()
