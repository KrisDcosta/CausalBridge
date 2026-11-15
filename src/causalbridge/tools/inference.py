"""Exact binary population interventions using only the supplied visible evidence.

Public functions enforce the same conservative evidence contracts as the verifier.
Enumeration is exponential and deliberately bounded for the project's small DAGs.
"""

from itertools import product
from math import fsum, prod

from causalbridge.schemas import Operation, Query, RuntimeCase, ToolRequest
from causalbridge.tools.graph import has_path
from causalbridge.verifier.contracts import check_preconditions

MAX_ENUMERATION_NODES = 12


def check_evidence(case: RuntimeCase, query: Query, operation: Operation) -> tuple[str, ...]:
    """Return missing contract requirements; unknown query variables raise ValueError."""
    request = ToolRequest(operation=operation, query=query, evidence_digest=case.evidence_digest())
    return check_preconditions(request, case)


def _require_evidence(case: RuntimeCase, query: Query, operation: Operation) -> None:
    missing = check_evidence(case, query, operation)
    if missing:
        raise ValueError("Missing preconditions: " + ", ".join(missing))


def _intervention(case: RuntimeCase, query: Query, treatment: int) -> float:
    if len(case.graph_nodes) > MAX_ENUMERATION_NODES:
        raise ValueError(f"Exact enumeration supports at most {MAX_ENUMERATION_NODES} nodes")
    cpts = {cpt.node: cpt for cpt in case.visible_cpts}
    # Fix both query variables; sum over the remaining variables, in any node order.
    remaining = [n for n in case.graph_nodes if n not in {query.cause, query.outcome}]

    def mass(bits):
        assignment = dict(zip(remaining, bits, strict=True))
        assignment.update({query.cause: treatment, query.outcome: 1})
        factors = []
        for node in case.graph_nodes:
            if node == query.cause:
                continue  # do(X=x) replaces X's mechanism with a point mass.
            cpt = cpts[node]
            key = "".join(str(assignment[parent]) for parent in cpt.parents)
            probability = cpt.p_one[key]
            factors.append(probability if assignment[node] else 1.0 - probability)
        return prod(factors)

    return fsum(mass(bits) for bits in product((0, 1), repeat=len(remaining)))


def compute_intervention(case: RuntimeCase, query: Query) -> float:
    """Return P(outcome=1 | do(cause=intervention_value)) by truncated factorization."""
    _require_evidence(case, query, "compute_intervention")
    return _intervention(case, query, query.intervention_value)


def compute_effect(case: RuntimeCase, query: Query) -> float:
    """Return the signed to-minus-from population contrast, without rounding."""
    _require_evidence(case, query, "compute_effect")
    if not has_path(case, query):
        return 0.0
    return _intervention(case, query, query.to_value) - _intervention(case, query, query.from_value)


def backdoor_adjustment(case: RuntimeCase, query: Query) -> float:
    """Return sum_z P(Y=1 | X=x,z) P(z), marginalizing extra joint variables."""
    _require_evidence(case, query, "backdoor_adjustment")
    joint = case.visible_joint
    # Presence and required variables are guaranteed by the evidence contract.
    rows = [
        (dict(zip(joint.variables, map(int, key), strict=True)), probability)
        for key, probability in joint.probabilities.items()
    ]
    terms = []
    for bits in product((0, 1), repeat=len(query.adjustment_set)):
        adjustment = dict(zip(query.adjustment_set, bits, strict=True))
        matching = [(a, p) for a, p in rows if all(a[n] == v for n, v in adjustment.items())]
        p_z = fsum(p for _, p in matching)
        p_xz = fsum(p for a, p in matching if a[query.cause] == query.intervention_value)
        p_yxz = fsum(
            p
            for a, p in matching
            if a[query.cause] == query.intervention_value and a[query.outcome] == 1
        )
        if p_xz <= 0:
            raise ValueError("Adjustment violates positivity")
        terms.append((p_yxz / p_xz) * p_z)
    return fsum(terms)
