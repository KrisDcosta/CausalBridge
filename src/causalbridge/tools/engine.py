"""Visible-only backend for deterministic graph and binary causal calculations."""

from causalbridge.schemas import RuntimeCase, ToolRequest, ToolResult
from causalbridge.tools.graph import has_path, valid_adjustment
from causalbridge.tools.inference import (
    backdoor_adjustment,
    compute_effect,
    compute_intervention,
)


class CausalEngineBackend:
    """Implement ToolBackend without loading oracle files or using reference answers."""

    def execute(self, request: ToolRequest, case: RuntimeCase) -> ToolResult:
        try:
            # Revalidate a snapshot: frozen models can still contain mutable dictionaries.
            visible = RuntimeCase.model_validate_json(case.model_dump_json())
            if request.evidence_digest != visible.evidence_digest():
                raise ValueError("Evidence digest mismatch")
            request.query.bind(visible)
            query = request.query
            match request.operation:
                case "has_directed_path":
                    value = has_path(visible, query)
                case "is_valid_adjustment_set":
                    value = valid_adjustment(visible, query)
                case "compute_intervention":
                    value = compute_intervention(visible, query)
                case "compute_effect":
                    value = compute_effect(visible, query)
                case "backdoor_adjustment":
                    value = backdoor_adjustment(visible, query)
                case _:
                    raise ValueError("Unsupported operation")
            return ToolResult(request=request, value=value)
        except (ValueError, KeyError, ArithmeticError) as exc:
            return ToolResult(request=request, error=str(exc))
