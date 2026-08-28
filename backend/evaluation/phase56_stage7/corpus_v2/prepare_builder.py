"""The preparation itself, as a pure function of the corpus and the manifest.

Phase M used to *be* this code, inline in a command that also wrote files.  It
is a module now for one reason: Phase V has to be able to compute the same
answer without trusting anything Phase M wrote.

That distinction is what makes the verification independent rather than
circular.  An attestation lets a later phase check that a runtime input is the
one that was attested; it cannot check that the attested preparation was the
*right* preparation, because an attacker who edits both files consistently
satisfies every cross-reference between them.  Phase V closes that by going
back to the two inputs nobody can forge without being noticed — the public
corpus archive, whose SHA-256 is published and frozen, and the augmentation
manifest, whose digest is published — and rebuilding.  Then it compares the
rebuild against the bytes on disk.

So the sharing here is deliberate and bounded.  Phase M and Phase V run the
same builder, which is what makes a byte-level comparison meaningful; but Phase
V calls it on the *original* corpus and manifest rather than on anything Phase M
produced, and compares its own output against the artifacts rather than reading
the artifacts' opinion of themselves.

The scan ordering is a contract, not an optimization.  The forbidden-key scan
runs over the raw payload **before** the payload is validated into models and
long before it is written, so a bundle naming a gold member never exists on disk
as a complete file.  Previously the file was written first and scanned after,
which meant the one artifact you would most want never to have existed was
exactly the artifact that did.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.phase56_stage7.contracts import PUBLIC_CORPUS_ZIP_SHA256
from evaluation.phase56_stage7.corpus_integrity import read_public_corpus_archive
from evaluation.phase56_stage7.corpus_preflight import load_public_cases
from evaluation.phase56_stage7.corpus_v2.canonical import file_sha256
from evaluation.phase56_stage7.corpus_v2.migration import (
    AugmentationManifestV1,
    ReviewStatus,
    archive_digest,
    assert_manifest_has_no_answer_authority,
    build_candidate_archive,
    record_fingerprint,
)
from evaluation.phase56_stage7.corpus_v2.projection import derived_authority_ids
from evaluation.phase56_stage7.corpus_v2.runtime_input import (
    RuntimeContextInputV2,
    ShadowRuntimeInputV2,
    assert_bundle_has_no_gold,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    RefusalCode,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import scoring_handle
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft


CORPUS_V2_PREPARE_BUILDER_VERSION = "phase56-stage7-corpus-v2-prepare-builder-v1"


def _context_identifier_sets(payload: dict[str, Any]) -> dict[str, list[str]]:
    authored = [
        *(item["entity_id"] for item in payload.get("entities") or []),
        *(item["event_id"] for item in payload.get("events") or []),
        *(item["interval_id"] for item in payload.get("motion_intervals") or []),
        *(item["quantity_id"] for item in payload.get("quantities") or []),
        *(item["query_id"] for item in payload.get("queries") or []),
    ]
    return {
        "entities": [item["entity_id"] for item in payload.get("entities") or []],
        "intervals": [
            item["interval_id"] for item in payload.get("motion_intervals") or []
        ],
        "events": [item["event_id"] for item in payload.get("events") or []],
        "evidence": [
            item["evidence_id"] for item in payload.get("source_evidence") or []
        ],
        "interactions": [
            item["interaction_id"] for item in payload.get("interactions") or []
        ],
        "queries": [item["query_id"] for item in payload.get("queries") or []],
        "authored": authored,
    }


def _artifact_body(payload: Any) -> str:
    """The on-disk spelling of a prepared artifact.

    Indented and sorted, and *not* the canonical digest spelling: these files
    are read by people as well as by verifiers, and the digest is computed
    separately over the canonical form so the two never depend on each other's
    formatting.  There is no timestamp and no path in any of them, which is what
    makes two independent runs byte-identical.
    """

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )


@dataclass(frozen=True)
class PreparedCampaignV1:
    """Everything one preparation produces, before anything is written.

    Bodies as well as digests, because Phase V's comparison against the
    candidate archive is a comparison of *bytes*: a rebuild that agreed about
    every hash while disagreeing about the file would be a rebuild of something
    else.

    Deliberately a dataclass and not a `FrozenStrictModel`.  The strict model
    strips surrounding whitespace from every string field, which would quietly
    eat the trailing newline these bodies end with — and the file SHA-256 of a
    body is computed over exactly the bytes that reach disk.  A container that
    silently rewrote its own contents is the last thing an evidence chain
    needs.
    """

    original_v1_archive_sha256: str
    augmentation_manifest_digest: str
    augmentation_manifest_file_sha256: str
    candidate_archive_digest: str
    candidate_body: str
    candidate_file_sha256: str
    runtime_input: ShadowRuntimeInputV2
    runtime_input_body: str
    runtime_input_file_sha256: str
    expected_context_count: int
    unresolved_augmentation_count: int


class PrepareBuildRefused(RuntimeError):
    """A preparation that cannot be built honestly is not built at all."""


def build_prepared_campaign(
    *,
    corpus_archive: Path,
    manifest: Path,
    expected_corpus_sha256: str = PUBLIC_CORPUS_ZIP_SHA256,
) -> PreparedCampaignV1:
    """Read the corpus and the manifest, and derive the whole preparation.

    Deterministic in the strict sense the deterministic-rebuild gate needs: the
    same archive and the same manifest produce the same bytes, with no clock,
    no path and no dict-ordering dependence anywhere in the result.

    Runs no pipeline, solves nothing, and compares no answer.  It reads the
    corpus — it has to, that is where the records are — and what leaves is a
    `ShadowRuntimeInputV2`, a type with no field an expectation is expressible
    in.
    """

    # Preserve the original call shape when the frozen Phase 56 identity is
    # used.  Several fail-closed controls replace the reader with a minimal
    # one-argument probe; forcing a new keyword through that path would change
    # the historical contract rather than extend it.  Only a separately named
    # campaign supplies the explicit alternate identity.
    if expected_corpus_sha256 == PUBLIC_CORPUS_ZIP_SHA256:
        inventory = read_public_corpus_archive(corpus_archive)
    else:
        inventory = read_public_corpus_archive(
            corpus_archive, expected_sha256=expected_corpus_sha256
        )
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    manifest_bytes = manifest.read_bytes()
    manifest_text = manifest_bytes.decode("utf-8")
    manifest_model = AugmentationManifestV1.model_validate_json(manifest_text)
    assert_manifest_has_no_answer_authority(json.loads(manifest_text))

    records = [case.model_dump(mode="json", warnings="none") for case in cases]
    projections = [project_case_to_draft(case) for case in cases]

    context_ids: dict[str, dict[str, list[str]]] = {}
    draft_payloads: dict[str, dict[str, Any]] = {}
    payloads: list[dict[str, Any] | None] = []
    for record, projection in zip(records, projections):
        draft = projection.draft
        payload = (
            None if draft is None else draft.model_dump(mode="json", warnings="none")
        )
        payloads.append(payload)
        fingerprint = record_fingerprint(record)
        if payload is not None:
            draft_payloads[fingerprint] = payload
        context_ids[fingerprint] = _context_identifier_sets(payload or {})

    migrated = build_candidate_archive(
        records, manifest_model, context_ids=context_ids, draft_payloads=draft_payloads
    )
    candidate_digest = archive_digest(migrated)
    candidate_body = _artifact_body(
        {
            "schema_version": manifest_model.schema_version,
            "original_v1_archive_sha256": inventory.archive_sha256,
            "augmentation_manifest_sha256": manifest_model.digest,
            "records": [item.model_dump(mode="json") for item in migrated],
        }
    )

    # --- raw payload, then the scan, then validation, then the digest --------
    # A forbidden key found here has never been written anywhere.
    raw_contexts: list[dict[str, Any]] = []
    for index, (projection, entry, payload) in enumerate(
        zip(projections, migrated, payloads)
    ):
        handle = scoring_handle(
            original_v1_archive_sha256=inventory.archive_sha256,
            context_index=index,
        )
        if payload is None:
            # Anticipated: the v1 record does not carry what a Draft needs.
            # The context stays in the bundle so the next phase inherits it,
            # and it carries nothing else — a refusal with the projection's
            # runtime outputs on it is a refusal nobody prepared.
            raw_contexts.append(
                {
                    "scoring_handle": handle,
                    "context_index": index,
                    "prepared_state": LedgerState.projection_refused.value,
                    "refusal_code": RefusalCode.projection_refused_no_draft.value,
                    "draft_payload": None,
                }
            )
            continue
        raw_contexts.append(
            {
                "scoring_handle": handle,
                "context_index": index,
                "prepared_state": LedgerState.runtime_completed.value,
                "refusal_code": None,
                "draft_payload": payload,
                "problem_text": projection.problem_text,
                "augmentation": entry.augmentation.model_dump(mode="json"),
                "derived_authority_ids": list(
                    derived_authority_ids(entry.augmentation)
                ),
                "projection_terminal": getattr(projection.terminal, "value", None),
                "sanitized_reason": projection.sanitized_reason,
                "environment_scoped_quantity_ids": list(
                    projection.environment_scoped_quantity_ids
                ),
                "segment_internal_event_ids": list(
                    projection.segment_internal_event_ids
                ),
                "approvable_assumption_ids": list(
                    projection.approvable_assumption_ids
                ),
                "known_symbol_ids": list(projection.known_symbol_ids),
                "unknown_symbol_ids": list(projection.unknown_symbol_ids),
                "event_authority_gaps": [
                    list(pair) for pair in projection.event_authority_gaps
                ],
            }
        )

    raw_bundle: dict[str, Any] = {
        "original_v1_archive_sha256": inventory.archive_sha256,
        "augmentation_manifest_sha256": manifest_model.digest,
        "candidate_archive_sha256": candidate_digest,
        "unresolved_augmentation_count": sum(
            1 for item in migrated if item.review_status is ReviewStatus.unresolved
        ),
        "contexts": raw_contexts,
    }
    # 1. raw payload assembled.  2. the scan, before anything is validated or
    # written.  3. schema validation, which is where the cross-field contract
    # between state, refusal code and draft payload is enforced.
    assert_bundle_has_no_gold(raw_bundle)
    assert_bundle_has_no_gold(json.loads(candidate_body))
    bundle = ShadowRuntimeInputV2.model_validate_json(
        json.dumps(raw_bundle, ensure_ascii=False, allow_nan=False)
    )
    if len(bundle.contexts) != len(cases):
        raise PrepareBuildRefused("shadow_context_count_mismatch")

    runtime_input_body = _artifact_body(bundle.model_dump(mode="json"))
    return PreparedCampaignV1(
        original_v1_archive_sha256=inventory.archive_sha256,
        augmentation_manifest_digest=manifest_model.digest,
        augmentation_manifest_file_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        candidate_archive_digest=candidate_digest,
        candidate_body=candidate_body,
        candidate_file_sha256=file_sha256(candidate_body),
        runtime_input=bundle,
        runtime_input_body=runtime_input_body,
        runtime_input_file_sha256=file_sha256(runtime_input_body),
        expected_context_count=len(bundle.contexts),
        unresolved_augmentation_count=bundle.unresolved_augmentation_count,
    )


__all__ = [
    "CORPUS_V2_PREPARE_BUILDER_VERSION",
    "PrepareBuildRefused",
    "PreparedCampaignV1",
    "build_prepared_campaign",
]
