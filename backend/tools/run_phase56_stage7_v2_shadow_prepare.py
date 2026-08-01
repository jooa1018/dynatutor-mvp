"""Phase M — build the v2 candidate archive and the runtime input bundle.

This command reads the corpus and the manifest, migrates one against the other,
and writes two files: the candidate archive, and the gold-free bundle the
runtime phase will be given.  It runs no pipeline and compares no answer.

Splitting it out is what lets Phase R be provably gold-free.  When one process
did all three jobs it held `PublicCorpusCaseV1` objects — which contain `gold` —
from the first line to the last, so the claim "the runtime never saw an expected
answer" could only ever be a claim about discipline.  Here the corpus is read
once, by a command that does not solve, and what leaves is a
`ShadowRuntimeInputV2`: a type with no field an expectation could be written
into.

Every context in the corpus gets an entry in the bundle, including the ones
whose v1 record cannot be projected.  A refused context that stayed in the file
is a context the next phase still has to account for; a refused context that was
dropped here would be one nobody could notice was missing.

Exit 0 when the bundle was written, 2 when it could not be built honestly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import load_public_cases  # noqa: E402
from evaluation.phase56_stage7.corpus_v2.migration import (  # noqa: E402
    AugmentationManifestV1,
    ReviewStatus,
    archive_digest,
    assert_manifest_has_no_answer_authority,
    build_candidate_archive,
    record_fingerprint,
)
from evaluation.phase56_stage7.corpus_v2.projection import (  # noqa: E402
    derived_authority_ids,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (  # noqa: E402
    RuntimeContextInputV2,
    ShadowRuntimeInputV2,
    assert_bundle_has_no_gold,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (  # noqa: E402
    LedgerState,
    RefusalCode,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (  # noqa: E402
    scoring_handle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (  # noqa: E402
    project_case_to_draft,
)

PREPARE_FAILURE_EXIT = 2


def _write_atomic(path: Path, body: str) -> str:
    """Write a file that is either wholly there or not there at all.

    A half-written artifact is worse than a missing one: it has a name, a size
    and a hash, and nothing about it says it is a fragment.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--runtime-input", type=Path, required=True)
    args = parser.parse_args()

    inventory = read_public_corpus_archive(args.corpus_archive)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    manifest_text = args.manifest.read_text(encoding="utf-8")
    manifest = AugmentationManifestV1.model_validate_json(manifest_text)
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
        records, manifest, context_ids=context_ids, draft_payloads=draft_payloads
    )
    candidate_sha = archive_digest(migrated)
    candidate_body = (
        json.dumps(
            {
                "schema_version": manifest.schema_version,
                "original_v1_archive_sha256": inventory.archive_sha256,
                "augmentation_manifest_sha256": manifest.digest,
                "records": [item.model_dump(mode="json") for item in migrated],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    candidate_file_sha = _write_atomic(args.candidate_archive, candidate_body)

    contexts: list[RuntimeContextInputV2] = []
    for index, (projection, entry, payload) in enumerate(
        zip(projections, migrated, payloads)
    ):
        handle = scoring_handle(
            original_v1_archive_sha256=inventory.archive_sha256,
            context_index=index,
        )
        if payload is None:
            # Anticipated: the v1 record does not carry what a Draft needs.
            # The context stays in the bundle so the next phase inherits it.
            contexts.append(
                RuntimeContextInputV2(
                    scoring_handle=handle,
                    context_index=index,
                    prepared_state=LedgerState.projection_refused,
                    refusal_code=RefusalCode.projection_refused_no_draft,
                )
            )
            continue
        contexts.append(
            RuntimeContextInputV2(
                scoring_handle=handle,
                context_index=index,
                prepared_state=LedgerState.runtime_completed,
                draft_payload=payload,
                problem_text=projection.problem_text,
                augmentation=entry.augmentation,
                derived_authority_ids=derived_authority_ids(entry.augmentation),
                projection_terminal=getattr(projection.terminal, "value", None),
                sanitized_reason=projection.sanitized_reason,
                environment_scoped_quantity_ids=(
                    projection.environment_scoped_quantity_ids
                ),
                segment_internal_event_ids=projection.segment_internal_event_ids,
                approvable_assumption_ids=projection.approvable_assumption_ids,
                known_symbol_ids=projection.known_symbol_ids,
                unknown_symbol_ids=projection.unknown_symbol_ids,
                event_authority_gaps=projection.event_authority_gaps,
            )
        )

    bundle = ShadowRuntimeInputV2(
        original_v1_archive_sha256=inventory.archive_sha256,
        augmentation_manifest_sha256=manifest.digest,
        candidate_archive_sha256=candidate_sha,
        unresolved_augmentation_count=sum(
            1 for item in migrated if item.review_status is ReviewStatus.unresolved
        ),
        contexts=tuple(contexts),
    )
    if len(bundle.contexts) != len(cases):
        print(
            "STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:shadow_context_count_mismatch",
            file=sys.stderr,
        )
        return PREPARE_FAILURE_EXIT

    bundle_body = (
        json.dumps(
            bundle.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    bundle_file_sha = _write_atomic(args.runtime_input, bundle_body)

    # The bundle is restricted rather than published, so the publication scan
    # is the wrong one — it rejects `problem_text`, which is legitimate runtime
    # input.  What the bundle may never carry is an expectation, and that is
    # what this checks, before the runtime phase can be handed one.
    assert_bundle_has_no_gold(json.loads(bundle_body))

    print(f"STAGE7_V2_PREPARE_ORIGINAL_V1_ARCHIVE_SHA256={inventory.archive_sha256}")
    print(f"STAGE7_V2_PREPARE_MANIFEST_SHA256={manifest.digest}")
    print(f"STAGE7_V2_PREPARE_CANDIDATE_ARCHIVE_SHA256={candidate_sha}")
    print(f"STAGE7_V2_PREPARE_CANDIDATE_FILE_SHA256={candidate_file_sha}")
    print(f"STAGE7_V2_PREPARE_RUNTIME_INPUT_DIGEST={bundle.digest}")
    print(f"STAGE7_V2_PREPARE_RUNTIME_INPUT_FILE_SHA256={bundle_file_sha}")
    print(f"STAGE7_V2_PREPARE_EXPECTED_CONTEXTS={len(bundle.contexts)}")
    print(
        "STAGE7_V2_PREPARE_PROJECTION_REFUSED="
        + str(
            sum(
                1
                for item in bundle.contexts
                if item.prepared_state is LedgerState.projection_refused
            )
        )
    )
    print("STAGE7_V2_PREPARE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
