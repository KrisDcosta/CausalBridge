"""Numerical summaries of displayed A/B rows, matching NumericSummary provenance."""

from math import fsum, sqrt

from causalbridge.discovery.anm_requests import validate_rows
from causalbridge.discovery.schemas import NumericSummary


def summarize_display_rows(rows: object) -> NumericSummary:
    """Return population std (ddof=0); correlation is null for a constant column.

    These summaries describe ONLY displayed rows, not a larger hidden tool sample.
    No values are dropped, imputed, rounded, or read from evaluator metadata.
    """
    pairs = validate_rows(rows)
    if not pairs:
        raise ValueError("Displayed sample must contain at least one row")
    columns = tuple(zip(*pairs, strict=True))
    means = tuple(fsum(column) / len(pairs) for column in columns)
    centered = tuple(
        tuple(x - mean for x in column) for column, mean in zip(columns, means, strict=True)
    )
    scales = tuple(sqrt(fsum(x * x for x in column) / len(pairs)) for column in centered)
    correlation = None
    if all(scale > 0 for scale in scales):
        covariance = fsum(a * b for a, b in zip(*centered, strict=True)) / len(pairs)
        correlation = max(-1.0, min(1.0, covariance / scales[0] / scales[1]))
    return NumericSummary(
        n_display=len(pairs),
        mean=means,
        std=scales,
        minimum=tuple(min(column) for column in columns),
        maximum=tuple(max(column) for column in columns),
        correlation=correlation,
    )
