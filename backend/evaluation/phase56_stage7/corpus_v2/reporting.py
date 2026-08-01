"""The v2 shadow score, kept structurally separate from the official one.

The danger this module exists to prevent is a sentence like "the score went to
47".  A v2 shadow result is produced against a *candidate* archive that does not
exist in the frozen corpus, using carriers a human authored after the fact.  It
says something real about whether the v2 contract can carry the physics, and it
says nothing whatever about the official v1 public score.

So the two are never the same object.  `ShadowScorecardV1` has no field named
like an official metric, carries its own archive and manifest hashes, and
`SCORE_CLASS` is stamped into every report it produces.  A caller cannot
accidentally add a shadow number to an official one, because there is no
official field to add it to.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Annotated, Any, Iterable

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256


CORPUS_V2_REPORTING_VERSION = "phase56-stage7-corpus-v2-reporting-v1"

# Stamped into every shadow report.  Not decorative: a reader who sees only a
# fragment of this artifact still learns it is not an official score.
SCORE_CLASS = "EXPERIMENTAL_V2_SHADOW"
OFFICIAL_SCORE_CLASS = "OFFICIAL_V1"

_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class ShadowContextResultV1(FrozenStrictModel):
    """One shadow context's outcome.  Privacy-safe by construction."""

    cohort_digest: Sha256
    augmented: bool
    carriers_supplied: tuple[_Token, ...] = ()
    baseline_rung: _Token
    shadow_rung: _Token
    baseline_solved: bool = False
    shadow_solved: bool = False
    shadow_correct: bool = False
    shadow_wrong: bool = False

    @property
    def newly_solved(self) -> bool:
        return self.shadow_solved and not self.baseline_solved

    @property
    def regressed(self) -> bool:
        """A context that solved before the carrier and does not after."""

        return self.baseline_solved and not self.shadow_solved


class ShadowScorecardV1(FrozenStrictModel):
    """The v2 shadow result.  Never an official score, structurally.

    There is deliberately no `supported`, no `observed_public_score`, and no
    `terminal_mapping` field here.  A number that cannot be named like an
    official metric cannot be quoted as one.
    """

    version: str = CORPUS_V2_REPORTING_VERSION
    score_class: str = SCORE_CLASS
    candidate_archive_sha256: Sha256
    augmentation_manifest_sha256: Sha256
    original_v1_archive_sha256: Sha256
    context_count: int = 0
    augmented_context_count: int = 0
    unresolved_augmentation_count: int = 0
    shadow_correct: int = 0
    shadow_wrong: int = 0
    shadow_unresolved: int = 0
    newly_solved: int = 0
    regressed: int = 0
    carrier_coverage: tuple[tuple[str, int], ...] = ()
    cohort_yield: tuple[tuple[str, int], ...] = ()
    migration_ambiguities: tuple[tuple[str, int], ...] = ()
    results: tuple[ShadowContextResultV1, ...] = Field(default=(), max_length=512)

    @property
    def digest(self) -> str:
        material = repr(self.model_dump(mode="json")).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    @property
    def cohort_yield_count(self) -> int:
        """How many distinct structural cohorts gained at least one solve."""

        return len(self.cohort_yield)


def build_shadow_scorecard(
    results: Iterable[ShadowContextResultV1],
    *,
    candidate_archive_sha256: str,
    augmentation_manifest_sha256: str,
    original_v1_archive_sha256: str,
    unresolved_augmentation_count: int = 0,
    migration_ambiguities: tuple[tuple[str, int], ...] = (),
) -> ShadowScorecardV1:
    """Aggregate shadow results, with every hash that identifies the run."""

    rows = tuple(results)
    coverage: Counter[str] = Counter()
    yields: Counter[str] = Counter()
    for row in rows:
        for carrier in row.carriers_supplied:
            coverage[carrier] += 1
        if row.newly_solved:
            yields[row.cohort_digest] += 1
    return ShadowScorecardV1(
        candidate_archive_sha256=candidate_archive_sha256,
        augmentation_manifest_sha256=augmentation_manifest_sha256,
        original_v1_archive_sha256=original_v1_archive_sha256,
        context_count=len(rows),
        augmented_context_count=sum(1 for row in rows if row.augmented),
        unresolved_augmentation_count=unresolved_augmentation_count,
        shadow_correct=sum(1 for row in rows if row.shadow_correct),
        shadow_wrong=sum(1 for row in rows if row.shadow_wrong),
        shadow_unresolved=sum(
            1 for row in rows if not row.shadow_solved and not row.shadow_wrong
        ),
        newly_solved=sum(1 for row in rows if row.newly_solved),
        regressed=sum(1 for row in rows if row.regressed),
        carrier_coverage=tuple(sorted(coverage.items())),
        cohort_yield=tuple(sorted(yields.items())),
        migration_ambiguities=migration_ambiguities,
    )


def scorecard_as_dict(scorecard: ShadowScorecardV1) -> dict[str, Any]:
    """The shadow report as plain JSON, with its class stamped at the top."""

    payload = scorecard.model_dump(mode="json")
    payload["digest"] = scorecard.digest
    payload["score_class"] = SCORE_CLASS
    payload["is_official_score"] = False
    payload["official_score_note"] = (
        "This is a v2 candidate shadow measurement against an out-of-tree "
        "archive that is not the frozen public corpus. It is not the official "
        "v1 public score and must never be reported as one."
    )
    return payload


def assert_scores_are_separated(
    official: dict[str, Any], shadow: dict[str, Any]
) -> None:
    """Refuse a report that merges the two classes.

    Called before either artifact is written.  The check is deliberately blunt:
    an official payload that carries a shadow field, or a shadow payload that
    carries an official one, is a report a reader could quote either way.
    """

    if shadow.get("score_class") != SCORE_CLASS:
        raise ValueError("shadow report is not stamped as a shadow score")
    if shadow.get("is_official_score") is not False:
        raise ValueError("shadow report must state that it is not official")
    official_only = {"observed_public_score", "authority_accepted_score", "lane_b"}
    if official_only & set(shadow):
        raise ValueError("shadow report carries an official-score field")
    shadow_only = {
        "candidate_archive_sha256",
        "augmentation_manifest_sha256",
        "shadow_correct",
        "newly_solved",
    }
    if shadow_only & set(official):
        raise ValueError("official report carries a shadow-score field")


__all__ = [
    "CORPUS_V2_REPORTING_VERSION",
    "OFFICIAL_SCORE_CLASS",
    "SCORE_CLASS",
    "ShadowContextResultV1",
    "ShadowScorecardV1",
    "assert_scores_are_separated",
    "build_shadow_scorecard",
    "scorecard_as_dict",
]
