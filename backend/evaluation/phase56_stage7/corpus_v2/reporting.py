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

from collections import Counter
from typing import Annotated, Any, Iterable

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.canonical import canonical_digest


CORPUS_V2_REPORTING_VERSION = "phase56-stage7-corpus-v2-reporting-v1"
CORPUS_V2_SCORED_REPORTING_VERSION = "phase56-stage7-corpus-v2-scored-reporting-v2"

# Stamped into every shadow report.  Not decorative: a reader who sees only a
# fragment of this artifact still learns it is not an official score.
SCORE_CLASS = "EXPERIMENTAL_V2_SHADOW"
# The scored class is its own name.  A V1 report says a shadow run happened; a
# scored report says its answers were compared to the gold, which is a strictly
# stronger claim and must not be readable off the older stamp.
SCORED_SCORE_CLASS = "EXPERIMENTAL_V2_SHADOW_SCORED"
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
        """Over the shared canonical JSON, never over a `repr`.

        `repr` of a dict is a Python-implementation-dependent string that also
        encodes insertion order, so a verifier reproducing this number had to
        reproduce the interpreter rather than the content.  Every digest in
        this evaluation now goes through one canonicalization.
        """

        return canonical_digest(self.model_dump(mode="json"))

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


class ShadowScorecardV2(FrozenStrictModel):
    """The gold-scored v2 shadow result.  Still never an official score.

    A separate version rather than new fields on `ShadowScorecardV1`, because
    the two mean different things and a reader must not have to know which
    runner produced a given artifact to know whether `wrong: 0` was measured.
    A V1 report's `shadow_wrong` was only ever "nothing compared"; a V2
    report's `newly_solved_wrong` is a comparison that ran.

    `newly_solved_unscored` exists so the gap can never hide inside the other
    two.  An accepted shadow run has it at zero, and a run that does not is a
    run whose yield has not been shown correct.
    """

    version: str = CORPUS_V2_SCORED_REPORTING_VERSION
    score_class: str = SCORED_SCORE_CLASS
    scorer_version: str = CORPUS_V2_SCORED_REPORTING_VERSION
    runtime_contract_version: str = ""
    candidate_archive_sha256: Sha256
    augmentation_manifest_sha256: Sha256
    original_v1_archive_sha256: Sha256
    runtime_snapshot_sha256: Sha256
    exact_code_head: Annotated[str, StringConstraints(max_length=64)] | None = None
    # Which preparation this score is a score *of*.  Carried on the scorecard
    # rather than only on the snapshot, so the artifact a reader quotes and the
    # artifact a verifier checks name the same preparation.  Without them a
    # scorecard was attributable to a corpus and a commit but not to a
    # population, and a laundered population has the same corpus and commit as
    # an honest one.
    prepare_attestation_digest: Sha256 | None = None
    runtime_input_digest: Sha256 | None = None
    prepared_state_map_digest: Sha256 | None = None
    refusal_handle_set_digest: Sha256 | None = None
    expected_handle_set_digest: Sha256 | None = None
    campaign_seal_name: _Token | None = None
    expected_context_count: int = 0
    context_count: int = 0
    # Every way the run failed to account for every context, carried on the
    # scorecard rather than printed beside it.  This is the field that makes
    # the exit status and the artifact say the same thing: both read
    # `acceptance_failures`, and there is no path where one is a FAIL and the
    # other is a zero.
    completeness_failures: tuple[_Token, ...] = ()
    ledger_state_counts: tuple[tuple[str, int], ...] = ()
    ledger_refusal_counts: tuple[tuple[str, int], ...] = ()
    augmented_context_count: int = 0
    unresolved_augmentation_count: int = 0
    baseline_solved: int = 0
    shadow_solved: int = 0
    newly_solved: int = 0
    newly_solved_correct: int = 0
    newly_solved_wrong: int = 0
    newly_solved_unscored: int = 0
    all_shadow_correct: int = 0
    all_shadow_wrong: int = 0
    all_shadow_unscored: int = 0
    forbidden_class_solve: int = 0
    regressed: int = 0
    query_binding_mismatch: int = 0
    scoring_defect_counts: tuple[tuple[str, int], ...] = ()
    carrier_coverage: tuple[tuple[str, int], ...] = ()
    cohort_yield: tuple[tuple[str, int], ...] = ()
    migration_ambiguities: tuple[tuple[str, int], ...] = ()

    @property
    def digest(self) -> str:
        """Over the shared canonical JSON, never over a `repr`.

        `repr` of a dict is a Python-implementation-dependent string that also
        encodes insertion order, so a verifier reproducing this number had to
        reproduce the interpreter rather than the content.  Every digest in
        this evaluation now goes through one canonicalization.
        """

        return canonical_digest(self.model_dump(mode="json"))

    @property
    def cohort_yield_count(self) -> int:
        return len(self.cohort_yield)

    @property
    def acceptance_failures(self) -> tuple[str, ...]:
        """Every reason this run may not be reported as an accepted measurement.

        Kept as a list rather than a boolean so a caller reports what failed
        instead of only that something did.  A newly solved context nobody
        could score is on this list: an unscored yield is not a yield.
        """

        failures: list[str] = []
        if self.newly_solved_wrong:
            failures.append("newly_solved_wrong")
        if self.newly_solved_unscored:
            failures.append("newly_solved_unscored")
        if self.all_shadow_wrong:
            failures.append("all_shadow_wrong")
        if self.forbidden_class_solve:
            failures.append("forbidden_class_solve")
        if self.regressed:
            failures.append("regressed")
        if self.query_binding_mismatch:
            failures.append("query_binding_mismatch")
        # A run that lost a context fails here rather than reporting the
        # counts of the contexts it kept.  Listed last only because the others
        # are older; a completeness failure is the most serious of them, since
        # the remaining numbers are about an unknown subset.
        failures.extend(self.completeness_failures)
        return tuple(failures)


def build_scored_shadow_scorecard(
    scored: Iterable[Any],
    totals: Any,
    *,
    snapshot: Any,
    carrier_coverage: tuple[tuple[str, int], ...] = (),
    completeness_failures: Iterable[str] = (),
) -> ShadowScorecardV2:
    """Aggregate a scored shadow run against the snapshot it was scored from.

    Every identifying hash is taken from the snapshot rather than passed in
    again, so a report cannot claim to describe a run it was not built from.
    The completeness failures are the union of the snapshot's own and the
    scorer's pairing check, so the artifact records not only what the counts
    were but whether they were counts of the whole corpus.
    """

    rows = tuple(scored)
    binding = snapshot.prepare_binding
    return ShadowScorecardV2(
        runtime_contract_version=snapshot.runtime_contract_version,
        candidate_archive_sha256=snapshot.candidate_archive_sha256,
        augmentation_manifest_sha256=snapshot.augmentation_manifest_sha256,
        original_v1_archive_sha256=snapshot.original_v1_archive_sha256,
        runtime_snapshot_sha256=snapshot.runtime_snapshot_digest,
        exact_code_head=snapshot.exact_code_head,
        prepare_attestation_digest=binding.prepare_attestation_digest,
        runtime_input_digest=binding.runtime_input_digest,
        prepared_state_map_digest=binding.prepared_state_map_digest,
        refusal_handle_set_digest=binding.refusal_handle_set_digest,
        expected_handle_set_digest=binding.expected_handle_set_digest,
        campaign_seal_name=binding.campaign_seal_name,
        expected_context_count=snapshot.expected_context_count,
        completeness_failures=tuple(
            sorted(set(completeness_failures) | set(snapshot.completeness_failures()))
        ),
        ledger_state_counts=snapshot.ledger_state_counts,
        ledger_refusal_counts=snapshot.ledger_refusal_counts,
        context_count=snapshot.context_count,
        augmented_context_count=snapshot.augmented_context_count,
        unresolved_augmentation_count=snapshot.unresolved_augmentation_count,
        baseline_solved=sum(1 for row in snapshot.records if row.baseline_solved),
        shadow_solved=sum(1 for row in rows if row.shadow_solved),
        newly_solved=totals.newly_solved,
        newly_solved_correct=totals.newly_solved_correct,
        newly_solved_wrong=totals.newly_solved_wrong,
        newly_solved_unscored=totals.newly_solved_unscored,
        all_shadow_correct=totals.all_shadow_correct,
        all_shadow_wrong=totals.all_shadow_wrong,
        all_shadow_unscored=totals.all_shadow_unscored,
        forbidden_class_solve=totals.forbidden_class_solve,
        regressed=totals.regressed,
        query_binding_mismatch=totals.query_binding_mismatch,
        scoring_defect_counts=totals.defect_counts,
        carrier_coverage=carrier_coverage,
        cohort_yield=totals.cohort_yield,
        migration_ambiguities=snapshot.migration_ambiguities,
    )


def scored_scorecard_as_dict(scorecard: ShadowScorecardV2) -> dict[str, Any]:
    """The scored shadow report as plain JSON, with its class stamped at the top.

    No per-context row reaches this payload.  The scoring handles exist to pair
    a runtime record with its gold case inside the scorer and have no business
    in a published artifact, so they are not carried here at all.
    """

    payload = scorecard.model_dump(mode="json")
    payload["digest"] = scorecard.digest
    payload["score_class"] = SCORED_SCORE_CLASS
    payload["is_official_score"] = False
    payload["acceptance_failures"] = list(scorecard.acceptance_failures)
    payload["official_score_note"] = (
        "This is a gold-scored v2 candidate shadow measurement against an "
        "out-of-tree archive that is not the frozen public corpus. It is not "
        "the official v1 public score and must never be reported as one, nor "
        "added to one."
    )
    return payload


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

    if shadow.get("score_class") not in (SCORE_CLASS, SCORED_SCORE_CLASS):
        raise ValueError("shadow report is not stamped as a shadow score")
    if shadow.get("is_official_score") is not False:
        raise ValueError("shadow report must state that it is not official")
    official_only = {"observed_public_score", "authority_accepted_score", "lane_b"}
    if official_only & set(shadow):
        raise ValueError("shadow report carries an official-score field")
    shadow_only = {
        "candidate_archive_sha256",
        "augmentation_manifest_sha256",
        "runtime_snapshot_sha256",
        "shadow_correct",
        "newly_solved",
        "newly_solved_correct",
    }
    if shadow_only & set(official):
        raise ValueError("official report carries a shadow-score field")


__all__ = [
    "CORPUS_V2_REPORTING_VERSION",
    "CORPUS_V2_SCORED_REPORTING_VERSION",
    "OFFICIAL_SCORE_CLASS",
    "SCORE_CLASS",
    "SCORED_SCORE_CLASS",
    "ShadowContextResultV1",
    "ShadowScorecardV1",
    "ShadowScorecardV2",
    "assert_scores_are_separated",
    "build_scored_shadow_scorecard",
    "build_shadow_scorecard",
    "scorecard_as_dict",
    "scored_scorecard_as_dict",
]
