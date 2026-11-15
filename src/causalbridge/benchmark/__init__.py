"""Synthetic benchmark generation and development witness validation."""

from causalbridge.benchmark.generator import generate_cpts, generate_dag
from causalbridge.benchmark.witness import observational_marginal, validate_witness

__all__ = ["generate_cpts", "generate_dag", "observational_marginal", "validate_witness"]
