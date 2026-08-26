"""Phase 57 repository-reproducible public evaluation.

This package is a successor measurement, not a continuation of the missing
historical Phase 56 Stage 7 evidence chain.  It deliberately reuses the mature
Phase 56 corpus-v2 runtime and scorer while binding them to a separately named,
repository-contained public fixture population.
"""

from evaluation.phase57_reproducible.contracts import (
    PHASE57_CAMPAIGN_ID,
    PHASE57_CAMPAIGN_SEAL_NAME,
    PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    phase57_public_evaluation_contract,
)

__all__ = [
    "PHASE57_CAMPAIGN_ID",
    "PHASE57_CAMPAIGN_SEAL_NAME",
    "PHASE57_REPRODUCIBLE_ARCHIVE_SHA256",
    "phase57_public_evaluation_contract",
]
