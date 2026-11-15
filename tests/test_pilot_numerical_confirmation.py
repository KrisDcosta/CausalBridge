"""Anish's independent numeric check of Arunima's merged pilot/oracle records.

These tests consume evaluator models only in offline validation, never runtime.
The reference engine and benchmark witness calculation are not used as the oracle.
"""

from fractions import Fraction
from itertools import product
from math import prod

import pytest

from causalbridge.benchmark.pilot import build_small_pilot
from causalbridge.schemas import Query, RuntimeCase, ToolRequest
from causalbridge.tools.engine import CausalEngineBackend
from causalbridge.tools.inference import compute_effect


def exact_observational_joint(model):
    rows = []
    for bits in product((0, 1), repeat=len(model.graph_nodes)):
        assignment = dict(zip(model.graph_nodes, bits, strict=True))
        factors = []
        for cpt in model.visible_cpts:
            key = "".join(str(assignment[p]) for p in cpt.parents)
            p = Fraction(str(cpt.p_one[key]))
            factors.append(p if assignment[cpt.node] else 1 - p)
        rows.append((assignment, prod(factors)))
    assert sum(p for _, p in rows) == 1
    return rows


def exact_ipw_effect(model, query):
    treatment = next(c for c in model.visible_cpts if c.node == query.cause)
    values = {}
    for x in (query.from_value, query.to_value):
        total = Fraction(0)
        for a, p in exact_observational_joint(model):
            if a[query.cause] != x or a[query.outcome] != 1:
                continue
            key = "".join(str(a[parent]) for parent in treatment.parents)
            propensity = Fraction(str(treatment.p_one[key]))
            if x == 0:
                propensity = 1 - propensity
            total += p / propensity
        values[x] = total
    return values[query.to_value] - values[query.from_value]


def test_same_visible_marginal_opposite_effect_witness_confirmed_independently():
    cases, labels = build_small_pilot()
    label = next(row for row in labels if row["case_id"] == "G001_sign_xy")
    query = Query.model_validate(label["query"])
    effects = []
    for raw in label["oracle_models"]:
        model = RuntimeCase.model_validate(raw)
        joint = exact_observational_joint(model)
        for x, y in product((0, 1), repeat=2):
            assert sum(p for a, p in joint if a["X"] == x and a["Y"] == y) == Fraction(1, 4)
        exact = exact_ipw_effect(model, query)
        effects.append(exact)
        assert compute_effect(model, query) == pytest.approx(float(exact), abs=1e-12, rel=0)
    assert effects == [Fraction(3, 10), Fraction(-3, 10)]
    visible = next(case for case in cases if case.case_id == label["case_id"])
    request = ToolRequest(
        operation="compute_effect", query=query, evidence_digest=visible.evidence_digest()
    )
    assert CausalEngineBackend().execute(request, visible).value is None


def test_all_pilot_numeric_labels_match_independent_rational_references():
    _, labels = build_small_pilot()
    for label in labels:
        query = Query.model_validate(label["query"])
        if query.question_type == "reachability":
            continue
        exacts = []
        for raw in label["oracle_models"]:
            model = RuntimeCase.model_validate(raw)
            exact = exact_ipw_effect(model, query)
            exacts.append(exact)
            assert compute_effect(model, query) == pytest.approx(float(exact), abs=1e-12, rel=0)
        if label["answerable"]:
            assert label["target_value"] == pytest.approx(float(exacts[0]), abs=1e-12, rel=0)
        else:
            assert len(set(exacts)) == 2
            assert exacts[0] * exacts[1] < 0
