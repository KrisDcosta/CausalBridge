"""Deterministic selection and matched public evidence construction."""

import hashlib
import json
import random
from statistics import mean, pstdev

from causalbridge.discovery.contracts import (
    DisplayRow,
    EvidenceEnvelope,
    EvidencePackage,
    MethodCard,
    RuntimePair,
    SelectedPair,
    SelectionRecord,
    SelectionSpec,
    Summary,
)

QUESTION = "Which direction is more plausible, A -> B or B -> A? You may abstain."


def canonical_json(value) -> str:
    """Python JSON v1: normalized signed zero, sorted keys, finite numbers only."""

    def normalize(item):
        if isinstance(item, float) and item == 0:
            return 0.0
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(v) for v in item]
        return item

    return json.dumps(
        normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sample_digest(rows) -> str:
    return digest({"convention": "ordered-ab-float-v1", "rows": rows})


def rng(seed: int, case_id: str, purpose: str) -> random.Random:
    return random.Random(int(digest([seed, case_id, purpose]), 16))


def select_pair(pair: RuntimePair, spec: SelectionSpec | None = None) -> SelectedPair:
    spec = spec or SelectionSpec()
    order = (1, 0) if rng(spec.mapping_seed, pair.case_id, "mapping").getrandbits(1) else (0, 1)
    indices = tuple(
        sorted(
            rng(spec.sample_seed, pair.case_id, "method").sample(
                range(len(pair.rows)), min(spec.method_limit, len(pair.rows))
            )
        )
    )
    display = tuple(
        sorted(
            rng(spec.display_seed, pair.case_id, "display").sample(
                indices, min(spec.display_limit, len(indices))
            )
        )
    )
    rows = tuple(tuple(row[i] for i in order) for row in pair.rows)
    method_rows, display_rows = tuple(rows[i] for i in indices), tuple(rows[i] for i in display)
    return SelectedPair(
        case_id=pair.case_id,
        variables=tuple(pair.variables[i] for i in order),
        method_rows=method_rows,
        display_rows=display_rows,
        method_sample_digest=sample_digest(method_rows),
        display_sample_digest=sample_digest(display_rows),
        selection=SelectionRecord(
            case_id=pair.case_id,
            source_digest=digest(pair.model_dump()),
            spec=spec,
            column_order=order,
            method_indices=indices,
            display_indices=display,
        ),
    )


def summarize(rows) -> tuple[Summary, Summary]:
    return tuple(
        Summary(
            n=len(rows),
            minimum=min(c),
            maximum=max(c),
            mean=float(mean(c)),
            population_std=float(pstdev(c)),
        )
        for c in zip(*rows, strict=True)
    )


def build_packages(selected: SelectedPair, method: MethodCard) -> tuple[EvidenceEnvelope, ...]:
    # Revalidate private selection; do not trust a mutable/misbound handoff.
    if sample_digest(selected.method_rows) != selected.method_sample_digest:
        raise ValueError("Selected method sample digest mismatch")
    if sample_digest(selected.display_rows) != selected.display_sample_digest:
        raise ValueError("Selected display sample digest mismatch")
    if method.sample_digest != selected.method_sample_digest:
        raise ValueError("Diagnostic belongs to a different method sample")
    if method.n_selected != len(selected.method_rows):
        raise ValueError("Diagnostic sample count mismatch")
    summaries = summarize(selected.display_rows)
    display = tuple(
        DisplayRow(evidence_id=f"rows:r{i:04d}", values=row)
        for i, row in enumerate(selected.display_rows, 1)
    )
    packages = []
    for package in ("E1", "E2", "E3", "E4"):
        named, numeric = package != "E2", package != "E1"
        ids = ("context:A", "context:B") if named else ()
        if numeric:
            ids += tuple(r.evidence_id for r in display) + ("summary:A", "summary:B")
        if package == "E4":
            ids += (method.evidence_id,)
        payload = EvidencePackage(
            case_id=selected.case_id,
            package=package,
            question=QUESTION,
            context=selected.variables if named else None,
            display_rows=display if numeric else (),
            summary=summaries if numeric else None,
            method=method if package == "E4" else None,
            evidence_ids=ids,
        )
        packages.append(
            EvidenceEnvelope(
                payload=payload,
                evidence_digest=digest(payload.model_dump(mode="json", exclude_none=True)),
                display_sample_digest=selected.display_sample_digest if numeric else None,
                method_sample_digest=selected.method_sample_digest if package == "E4" else None,
            )
        )
    return tuple(packages)
