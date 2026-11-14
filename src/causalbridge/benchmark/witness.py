"""Development checks for compatible complete binary-model witnesses.

Keep these complete models in benchmark/oracle code, never runtime input.
Intervention effects use the replaceable development numerical adapter until
Anish independently confirms the oracle calculations.
"""

from dataclasses import dataclass
from itertools import product
from math import isfinite, prod

from causalbridge.schemas import CPT, JointDistribution, Query, RuntimeCase, bit_keys
from causalbridge.tools.reference import intervention


@dataclass(frozen=True)
class WitnessValidation:
    visible_joint: JointDistribution | None
    first_effect: float
    second_effect: float


def observational_marginal(model: RuntimeCase, variables: tuple[str, ...]) -> JointDistribution:
    """Marginalize a complete model onto ordered visible variables."""
    if not variables or len(set(variables)) != len(variables):
        raise ValueError("Visible variables must be nonempty and unique")
    if not set(variables) <= set(model.graph_nodes):
        raise ValueError("Visible variables must belong to the model")
    cpts = {cpt.node: cpt for cpt in model.visible_cpts}
    if set(cpts) != set(model.graph_nodes):
        raise ValueError("Witness models require a complete CPT for every node")
    probabilities = {"".join(bits): 0.0 for bits in product("01", repeat=len(variables))}
    for bits in product((0, 1), repeat=len(model.graph_nodes)):
        assignment = dict(zip(model.graph_nodes, bits, strict=True))
        factors = []
        for node in model.graph_nodes:
            cpt = cpts[node]
            key = "".join(str(assignment[parent]) for parent in cpt.parents)
            p_one = cpt.p_one[key]
            factors.append(p_one if assignment[node] else 1 - p_one)
        visible_key = "".join(str(assignment[node]) for node in variables)
        probabilities[visible_key] += prod(factors)
    return JointDistribution(variables=variables, probabilities=probabilities)


def validate_witness(
    first: RuntimeCase,
    second: RuntimeCase,
    visible_joint: JointDistribution | None,
    query: Query,
    *,
    visible_cpts: tuple[CPT, ...] = (),
    tolerance: float = 1e-9,
    minimum_effect_difference: float = 1e-6,
    opposite_signs: bool = True,
) -> WitnessValidation:
    """Require the same DAG/evidence and different intervention effects.

    This checks a proposed pair; it does not search for witness models or
    independently certify the development adapter's numerical computation.
    """
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    if not isfinite(minimum_effect_difference) or minimum_effect_difference <= 0:
        raise ValueError("minimum_effect_difference must be finite and positive")
    if query.question_type not in {"effect_direction", "effect_magnitude"}:
        raise ValueError("Witness query must ask for an effect")
    if set(first.graph_nodes) != set(second.graph_nodes) or set(first.graph_edges) != set(
        second.graph_edges
    ):
        raise ValueError("Witness models must have the same DAG")
    if len({cpt.node for cpt in visible_cpts}) != len(visible_cpts):
        raise ValueError("Visible CPT constraints must not repeat nodes")
    for model in (first, second):
        query.bind(model)
        if model.assumptions is None or not model.assumptions.satisfied():
            raise ValueError("Witness models require satisfied causal assumptions")
        model_cpts = {cpt.node: cpt for cpt in model.visible_cpts}
        if set(model_cpts) != set(model.graph_nodes):
            raise ValueError("Witness models require a complete CPT for every node")
        if visible_joint is not None:
            actual = observational_marginal(model, visible_joint.variables)
            if any(
                abs(actual.probabilities[key] - expected) > tolerance
                for key, expected in visible_joint.probabilities.items()
            ):
                raise ValueError("Witness model disagrees with visible evidence")
        for visible in visible_cpts:
            if visible.node not in model_cpts or set(visible.parents) != set(
                model.graph().predecessors(visible.node)
            ):
                raise ValueError("Visible CPT constraint does not match the graph")
            actual_cpt = model_cpts[visible.node]
            for bits in bit_keys(len(visible.parents)):
                assignment = dict(zip(visible.parents, bits, strict=True))
                actual_key = "".join(assignment[parent] for parent in actual_cpt.parents)
                if abs(visible.p_one[bits] - actual_cpt.p_one[actual_key]) > tolerance:
                    raise ValueError("Witness model disagrees with visible CPT evidence")
    effects = tuple(
        intervention(model, query, query.to_value) - intervention(model, query, query.from_value)
        for model in (first, second)
    )
    if abs(effects[0] - effects[1]) < minimum_effect_difference:
        raise ValueError("Witness effects are insufficiently different")
    if opposite_signs and not (
        (effects[0] > tolerance and effects[1] < -tolerance)
        or (effects[1] > tolerance and effects[0] < -tolerance)
    ):
        raise ValueError("Witness effects must have opposite signs")
    return WitnessValidation(visible_joint, *effects)
