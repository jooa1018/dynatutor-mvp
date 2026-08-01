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
from typing import Annotated, Any, Mapping

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel, Sha256
from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)


CORPUS_V2_RUNTIME_INPUT_VERSION = "phase56-stage7-corpus-v2-runtime-input-v1"

_Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Token = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class RuntimeContextInputV2(FrozenStrictModel):
    """One context, as the runtime phase is permitted to see it.

    `draft_payload` is `None` exactly when the v1 record could not be projected
    — the anticipated refusal — and the entry still exists, carrying its handle
    and its reason.  That is the whole point: the refused context is *in* the
    bundle, so the runtime phase inherits a complete list of what it is
    accounting for rather than a list of what happened to survive.
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
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

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
                if isinstance(key, str) and key.casefold() in _FORBIDDEN_BUNDLE_KEYS:
                    raise RuntimeInputRefused(
                        f"the runtime input names a gold member: {key}"
                    )
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(value)


def load_runtime_input(body: str) -> ShadowRuntimeInputV2:
    """Re-read a bundle from its own bytes, or refuse it."""

    try:
        bundle = ShadowRuntimeInputV2.model_validate_json(body)
    except Exception as exc:  # noqa: BLE001 — re-raised as the typed refusal
        raise RuntimeInputRefused(
            f"the runtime input could not be read as one: {type(exc).__name__}"
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
    "RuntimeContextInputV2",
    "RuntimeInputRefused",
    "ShadowRuntimeInputV2",
    "assert_bundle_has_no_gold",
    "load_runtime_input",
]
