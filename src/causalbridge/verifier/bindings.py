"""Verifier-only receipts from trusted runtime storage, never evaluator records."""

from pydantic import model_validator

from causalbridge.discovery.schemas import Count, Digest, Identifier, Nonnegative, Seed
from causalbridge.schemas import Record


class ANMRequestBinding(Record):
    """Original request saved BEFORE ANM execution, not projected from its result.

    The producer is responsible for hashing the actual method sample/config and
    resolving opaque A/B IDs correctly. No method samples or labels are loaded
    by the checker. Counts and split settings are part of the saved request.
    """

    case_id: Identifier
    ab_mapping_id: Identifier
    sample_digest: Digest
    config_digest: Digest
    selected_row_count: Count
    training_row_count: Count
    evaluation_row_count: Count
    sampling_seed: Seed
    split_seed: Seed
    threshold: Nonnegative | None
    method_version: Identifier
    configuration_version: Identifier

    @model_validator(mode="after")
    def validate_counts(self):
        if self.training_row_count + self.evaluation_row_count != self.selected_row_count:
            raise ValueError("Request split counts must partition the method sample")
        return self


class VerificationContext(Record):
    """Independent receipt loaded by Kris from the original successful S1 cache.

    Save evidence identities and cached method-result digest before prediction,
    then bind proposal_digest on saving the parsed S1 output. Do not recompute
    these expected values from the candidate objects at verification time.
    method_request is loaded from the independently saved original ANM request.
    This receipt is a trusted input, not a cryptographic authentication scheme.
    """

    case_id: Identifier
    package_digest: Digest
    proposal_digest: Digest
    ab_mapping_id: Identifier
    mapping_seed: Seed
    display_sample_digest: Digest | None
    method_result_digest: Digest | None = None
    method_request: ANMRequestBinding | None = None
