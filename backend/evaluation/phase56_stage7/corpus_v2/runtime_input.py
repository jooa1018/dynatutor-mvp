"""What the runtime phase is allowed to be given.  No gold member is expressible.

The gold-isolation claim used to rest on a promise.  One process loaded the
whole `PublicCorpusCaseV1` — a model that *contains* `gold` — ran the pipeline
over it, and then opened the gold afterwards.  A test could show that the
runtime callback did not read an expected answer, but nothing could show that
the runtime phase could not have: the object was in scope the entire time, and
"Phase G opens the gold for the first time" was a statement about where the
lines were drawn in one file.

This module draws the line in the type system instead.  A
`ShadowRuntimeInputV2` carries the projected Draft, the source's own words, the
augmentation to attach, and the opaque pairing handle — and it has no field an
expected answer, expected terminal, expected failure code, family, case id or
split could be written into.  The runtime phase reads one of these and nothing
else, so the isolation is checkable by looking at what the process opened
rather than at what it did after opening it.

Building the bundle is its own phase, and it is neither of the two.  It reads
the corpus, migrates against the manifest, and writes a file; it never runs the
pipeline and never compares an answer.  Splitting it out is what leaves Phase R
with a single, gold-free input.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Mapping

from pydantic import Field, StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.canonical import canonical_json_bytes
from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)


CORPUS_V2_RUNTIME_INPUT_VERSION = "phase56-stage7-corpus-v2-runtime-input-v1"

_Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class PreparedStateConflict(str, Enum):
    """Why a context's declared state and its contents do not agree.

    Named values rather than free text, because these are the gate a negative
    control names.  "the bundle failed to validate" is not evidence that the
    laundering path is closed; ``runtime_completed_without_draft`` is.
    """

    runtime_completed_without_draft = "runtime_completed_without_draft"
    runtime_completed_with_refusal_code = "runtime_completed_with_refusal_code"
    projection_refused_with_draft = "projection_refused_with_draft"
    projection_refused_wrong_code = "projection_refused_wrong_code"
    projection_refused_with_runtime_authority = (
        "projection_refused_with_runtime_authority"
    )
    state_not_preparable = "prepared_state_not_reachable_from_prepare"


# The states Phase M can actually put a context into.  `migration_refused` is
# not one of them and this is a fact about the migration contract rather than an
# omission: `build_candidate_archive` either resolves an entry, leaves the
# record unresolved with an empty augmentation — which is still a preparable
# context — or raises `MigrationError` and aborts the whole preparation.  There
# is no path on which a migration refusal becomes a runtime input row, so
# admitting one here would be admitting a state no honest Phase M can produce.
# `runtime_failed` and `snapshot_rejected` are decided *after* preparation, by
# phases that have not run yet when this file is written.
PREPARABLE_STATES: frozenset[LedgerState] = frozenset(
    {LedgerState.runtime_completed, LedgerState.projection_refused}
)

# What a refused context may not carry.  Phase M leaves every one of these at
# its default for a context it could not project, so a refused row that has one
# is a row somebody assembled rather than one Phase M produced — which is the
# signature of a runtime-completed context relabelled as an allowed refusal.
_RUNTIME_ONLY_FIELDS: tuple[str, ...] = (
    "problem_text",
    "derived_authority_ids",
    "projection_terminal",
    "sanitized_reason",
    "environment_scoped_quantity_ids",
    "segment_internal_event_ids",
    "approvable_assumption_ids",
    "known_symbol_ids",
    "unknown_symbol_ids",
    "event_authority_gaps",
)


class RuntimeContextInputV2(FrozenStrictModel):
    """One context, as the runtime phase is permitted to see it.

    `draft_payload` is `None` exactly when the v1 record could not be projected
    — the anticipated refusal — and the entry still exists, carrying its handle
    and its reason.  That is the whole point: the refused context is *in* the
    bundle, so the runtime phase inherits a complete list of what it is
    accounting for rather than a list of what happened to survive.

    "Exactly when" is now enforced rather than described.  These three fields
    arrive from an external JSON document, and until this validator existed
    each was only checked against its own type: `prepared_state` had to be a
    member of the enum, `refusal_code` a member of its own, and `draft_payload`
    a mapping or null.  Nothing checked that they were talking about the same
    context.  So a solvable context could be handed back as

        prepared_state=projection_refused,
        refusal_code=projection_refused_no_draft,
        draft_payload=null

    and every downstream completeness rule agreed it was a legitimately refused
    context — one the contract *anticipates* — rather than a solvable one that
    had been excused out of the measurement.
    """

    scoring_handle: _Handle
    context_index: int = Field(ge=0)
    prepared_state: LedgerState
    refusal_code: RefusalCode | None = None
    draft_payload: dict[str, Any] | None = None
    problem_text: str | None = None
    augmentation: CorpusV2AugmentationV1 = Field(
        default_factory=CorpusV2AugmentationV1
    )
    derived_authority_ids: tuple[_Token, ...] = ()
    # The v1 projection's own outputs, carried so the runtime phase runs the
    # same lane it always did.  Every one of these is something the projection
    # *derived* from the v1 record's runtime fields — which assumptions the
    # source licenses, which symbols it names, which events scope which
    # interval.  `projection_terminal` is the projection's own disposition, not
    # an expected terminal: it says whether a Draft was built, and the corpus's
    # expectation about how the case should end is not reachable from here.
    projection_terminal: _Token | None = None
    sanitized_reason: _Token | None = None
    environment_scoped_quantity_ids: tuple[_Token, ...] = ()
    segment_internal_event_ids: tuple[_Token, ...] = ()
    approvable_assumption_ids: tuple[_Token, ...] = ()
    known_symbol_ids: tuple[_Token, ...] = ()
    unknown_symbol_ids: tuple[_Token, ...] = ()
    event_authority_gaps: tuple[tuple[_Token, _Token], ...] = ()

    @model_validator(mode="after")
    def validate_prepared_state(self) -> "RuntimeContextInputV2":
        """The state, the reason and the payload must describe one context.

        Fails closed on every disagreement, and raises the conflict's own name
        so the refusal is attributable.  A pydantic enum check alone would
        admit all of these: each field is individually well-typed, and the
        defect was never in any one of them.
        """

        if self.prepared_state not in PREPARABLE_STATES:
            raise ValueError(
                f"{PreparedStateConflict.state_not_preparable.value}: "
                f"{self.prepared_state.value}"
            )
        if self.prepared_state is LedgerState.runtime_completed:
            if self.draft_payload is None:
                raise ValueError(
                    PreparedStateConflict.runtime_completed_without_draft.value
                )
            if self.refusal_code is not None:
                raise ValueError(
                    PreparedStateConflict.runtime_completed_with_refusal_code.value
                )
            return self

        # projection_refused, the only other preparable state.
        if self.draft_payload is not None:
            raise ValueError(PreparedStateConflict.projection_refused_with_draft.value)
        if self.refusal_code is not RefusalCode.projection_refused_no_draft:
            raise ValueError(PreparedStateConflict.projection_refused_wrong_code.value)
        # A refusal that still carries the projection's runtime outputs is not a
        # refusal Phase M wrote.  Checked against the field defaults rather than
        # against a hand-kept list of values, so a new field is covered the day
        # it is added.
        for name in _RUNTIME_ONLY_FIELDS:
            default = type(self).model_fields[name].get_default(
                call_default_factory=True
            )
            if getattr(self, name) != default:
                raise ValueError(
                    f"{PreparedStateConflict.projection_refused_with_runtime_authority.value}"
                    f": {name}"
                )
        if not self.augmentation.is_empty:
            raise ValueError(
                f"{PreparedStateConflict.projection_refused_with_runtime_authority.value}"
                ": augmentation"
            )
        return self


class ShadowRuntimeInputV2(FrozenStrictModel):
    """Every context the runtime phase must account for, and nothing else."""

    version: str = CORPUS_V2_RUNTIME_INPUT_VERSION
    original_v1_archive_sha256: Sha256
    augmentation_manifest_sha256: Sha256
    candidate_archive_sha256: Sha256
    unresolved_augmentation_count: int = Field(default=0, ge=0)
    contexts: tuple[RuntimeContextInputV2, ...] = Field(default=(), max_length=512)

    @property
    def expected_handles(self) -> tuple[str, ...]:
        return tuple(item.scoring_handle for item in self.contexts)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class RuntimeInputRefused(RuntimeError):
    """A bundle that is not a runtime input is not run."""


# Every field that carries an expectation or a case identity, normalized.  The
# bundle's *type* already makes these unwritable at the top level; this scan is
# the belt to that braces, because `draft_payload` is an open mapping and a
# projection that ever started copying a gold member into a Draft would
# otherwise reach the runtime phase unnoticed.
_FORBIDDEN_BUNDLE_KEYS: frozenset[str] = frozenset(
    {
        "gold",
        "answers",
        "answer",
        "expected_answer",
        "expected_terminal",
        "future_expected_terminal",
        "phase55_expected_terminal",
        "expected_failure_codes",
        "expected_system_type",
        "reference_expression",
        "tolerance",
        "tolerance_abs",
        "family",
        "case_id",
        "split",
        "solver_output",
        "solution",
    }
)

# Matched on a normalized key rather than a casefolded one, so `expectedAnswer`,
# `expected-answer` and `Expected Answer` are the same forbidden name as
# `expected_answer`.  The manifest scan has always normalized this way; the
# bundle scan compared raw casefolded strings, so a spelling variant of a gold
# member would have passed it.
_FORBIDDEN_NORMALIZED: frozenset[str] = frozenset(
    re.sub(r"[^a-z0-9]", "", name.casefold()) for name in _FORBIDDEN_BUNDLE_KEYS
)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def assert_bundle_has_no_gold(value: Any) -> None:
    """Refuse a bundle naming any gold member or case identity, at any depth.

    Deliberately *not* `assert_privacy_safe_artifact`, which is the contract for
    a published artifact and rejects `problem_text`.  The bundle is restricted
    rather than published and the source's own words are legitimate runtime
    input — the projection aligns authored quotes against them.  What the
    bundle may never carry is an expectation, and that is what this checks.
    """

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if isinstance(key, str) and _normalized_key(key) in (
                    _FORBIDDEN_NORMALIZED
                ):
                    raise RuntimeInputRefused(
                        f"the runtime input names a gold member: {key}"
                    )
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)


def load_runtime_input(body: str) -> ShadowRuntimeInputV2:
    """Re-read a bundle from its own bytes, or refuse it.

    The gold scan runs on the **raw** parsed document, before the model sees
    it, and that ordering is the point rather than an implementation detail.
    `draft_payload` is an open mapping: pydantic will happily accept a
    ``{"gold": ...}`` nested six levels inside one, because the field's type is
    satisfied.  Scanning the validated model would also work, but scanning the
    raw document additionally covers anything the schema would have dropped or
    coerced on the way in, and it means the check has already run at the moment
    the trust boundary is crossed rather than after it.
    """

    try:
        raw = json.loads(body)
    except Exception as exc:  # noqa: BLE001 — re-raised as the typed refusal
        raise RuntimeInputRefused(
            f"the runtime input is not JSON: {type(exc).__name__}"
        ) from None
    assert_bundle_has_no_gold(raw)
    try:
        bundle = ShadowRuntimeInputV2.model_validate_json(body)
    except Exception as exc:  # noqa: BLE001 — re-raised as the typed refusal
        raise RuntimeInputRefused(
            f"the runtime input could not be read as one: {type(exc).__name__}: {exc}"
        ) from None
    if bundle.version != CORPUS_V2_RUNTIME_INPUT_VERSION:
        raise RuntimeInputRefused(
            f"the runtime input is version {bundle.version}, "
            f"not {CORPUS_V2_RUNTIME_INPUT_VERSION}"
        )
    handles = bundle.expected_handles
    if len(handles) != len(set(handles)):
        raise RuntimeInputRefused("two contexts share one scoring handle")
    return bundle


__all__ = [
    "CORPUS_V2_RUNTIME_INPUT_VERSION",
    "PREPARABLE_STATES",
    "PreparedStateConflict",
    "RuntimeContextInputV2",
    "RuntimeInputRefused",
    "ShadowRuntimeInputV2",
    "assert_bundle_has_no_gold",
    "load_runtime_input",
]
