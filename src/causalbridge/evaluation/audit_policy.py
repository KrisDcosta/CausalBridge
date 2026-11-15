"""Frozen Phase 1 specification copied for independent artifact checking.

Do not import runtime prompt construction here. A protocol change requires a new
policy version and review of this snapshot rather than silently accepting it.
"""

PROMPT_VERSION = "direction-v1"
QUESTION = "Which direction is more plausible, A -> B or B -> A? You may abstain."
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
