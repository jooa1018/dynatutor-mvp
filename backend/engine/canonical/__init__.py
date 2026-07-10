"""CanonicalProblem v2 data contracts.

The compatibility adapter lives in :mod:`engine.canonical.adapter` and is imported
lazily by the extractor to keep the legacy model dependency acyclic.
"""

from engine.canonical.models import (
    AssumptionRecord,
    CanonicalProblemV2,
    ExtractedFact,
    ParseCandidate,
    SystemTypeCandidate,
)

__all__ = [
    "AssumptionRecord",
    "CanonicalProblemV2",
    "ExtractedFact",
    "ParseCandidate",
    "SystemTypeCandidate",
]
