"""Build the v2 candidate archive, run the shadow evaluation, then score it.

Four artifacts come out, all outside the repository: the migrated candidate
archive, the frozen runtime snapshot, the gold-scored shadow report, and the
hashes that tie them to the v1 archive and the augmentation manifest they were
built from.

The shadow result is **not** the official score and this runner will not let it
be mistaken for one.  It prints under `STAGE7_V2_SHADOW_*` keys, the report
carries `score_class = EXPERIMENTAL_V2_SHADOW_SCORED`, and
`assert_scores_are_separated` runs before anything is written.

Every context is run twice through the same deterministic pipeline — once on
its v1 Draft, once with the augmentation attached — so a reported gain is a
measured difference and not a different run.

**Two phases, in this order, and the order is the contract.**

*Phase R* projects, compiles, solves and verifies, and reads no expected
answer, expected terminal, expected failure code, family or case id while doing
it.  It ends by freezing every runtime record into a `ShadowRuntimeSnapshotV2`
and hashing it.

*Phase G* opens the gold for the first time, pairs each gold case to a frozen
runtime record by an opaque handle, and compares — using the official strict
scorer's own comparator, not a second one.  It cannot re-run the pipeline: it
holds a snapshot, not a Draft.

Until this session Phase G did not exist.  `run_shadow_context` accepted an
optional comparator, this runner never passed one, and the resulting report said
`wrong: 0` — which meant "nothing was compared" and read as "nothing was wrong".
The three counts are now separate and a newly solved context that could not be
scored fails acceptance instead of disappearing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from engine.mechanics.contracts import MechanicsProblemDraftV1  # noqa: E402

from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import (  # noqa: E402
    load_public_cases,
)
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
from evaluation.phase56_stage7.corpus_v2.gold_scoring import (  # noqa: E402
    build_gold_index,
    score_shadow_snapshot,
    totals,
)
from evaluation.phase56_stage7.corpus_v2.reporting import (  # noqa: E402
    assert_scores_are_separated,
    build_scored_shadow_scorecard,
    scored_scorecard_as_dict,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (  # noqa: E402
    freeze_runtime_snapshot,
)
from evaluation.phase56_stage7.corpus_v2.shadow_runner import (  # noqa: E402
    assert_no_regression,
    assert_no_unaugmented_movement,
    run_shadow_context,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (  # noqa: E402
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (  # noqa: E402
    deterministic_token,
    run_lane_b_case,
)
from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)


class _Projected:
    """The shape `run_lane_b_case` expects, around an already-built Draft."""

    __slots__ = (
        "terminal",
        "problem_text",
        "draft",
        "sanitized_reason",
        "environment_scoped_quantity_ids",
        "segment_internal_event_ids",
        "approvable_assumption_ids",
        "known_symbol_ids",
        "unknown_symbol_ids",
        "event_authority_gaps",
    )

    def __init__(
        self, template: Any, draft: Any, derived_authorities: tuple[str, ...] = ()
    ) -> None:
        for name in self.__slots__:
            setattr(self, name, getattr(template, name, None))
        self.draft = draft
        if derived_authorities:
            self.approvable_assumption_ids = (
                *(self.approvable_assumption_ids or ()),
                *derived_authorities,
            )

    @property
    def projected(self) -> bool:
        return True


def _record_payload(case: Any) -> dict[str, Any]:
    """The v1 record's own canonical payload, used for its fingerprint."""

    return case.model_dump(mode="json", warnings="none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--runtime-snapshot", type=Path, required=True)
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--exact-code-head", type=str, default=None)
    parser.add_argument(
        "--record-regressions",
        action="store_true",
        help=(
            "record a carrier that takes a solve away instead of aborting. "
            "A measurement run needs the evidence; a release must not have it, "
            "so the default stays fail-closed."
        ),
    )
    args = parser.parse_args()

    inventory = read_public_corpus_archive(args.corpus_archive)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    manifest_text = args.manifest.read_text(encoding="utf-8")
    manifest = AugmentationManifestV1.model_validate_json(manifest_text)
    assert_manifest_has_no_answer_authority(json.loads(manifest_text))

    records = [_record_payload(case) for case in cases]
    projections = [project_case_to_draft(case) for case in cases]

    # The validator needs each record's own identifier sets so a carrier that
    # references something the source does not contain is refused, and the
    # merge contract needs each record's projected Draft so a carrier that
    # would restate a source field differently fails the migration itself.
    context_ids: dict[str, dict[str, list[str]]] = {}
    draft_payloads: dict[str, dict[str, Any]] = {}
    for record, projection in zip(records, projections):
        draft = projection.draft
        payload = (
            {} if draft is None else draft.model_dump(mode="json", warnings="none")
        )
        if draft is not None:
            draft_payloads[record_fingerprint(record)] = payload
        authored = [
            *(item["entity_id"] for item in payload.get("entities") or []),
            *(item["event_id"] for item in payload.get("events") or []),
            *(
                item["interval_id"]
                for item in payload.get("motion_intervals") or []
            ),
            *(item["quantity_id"] for item in payload.get("quantities") or []),
            *(item["query_id"] for item in payload.get("queries") or []),
        ]
        context_ids[record_fingerprint(record)] = {
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

    migrated = build_candidate_archive(
        records, manifest, context_ids=context_ids, draft_payloads=draft_payloads
    )
    candidate_sha = archive_digest(migrated)

    args.candidate_archive.parent.mkdir(parents=True, exist_ok=True)
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
    args.candidate_archive.write_text(candidate_body, encoding="utf-8")

    # --- PHASE R: runtime only.  No gold member is read below this line -----
    def _run_index(index: int, derived_authorities: tuple[str, ...] = ()):
        template = projections[index]

        def run(payload: dict[str, Any]):
            draft = MechanicsProblemDraftV1.model_validate(payload)
            # The approvable set is extended by exactly the ids the carriers
            # *derive* — never by an id a manifest named, because no manifest
            # can name one.  The authority bundle then re-checks that the
            # Draft's approved dispositions equal this set, so a carrier that
            # wrote an authority nobody declared still fails closed.
            return run_lane_b_case(
                _Projected(template, draft, derived_authorities),
                execution_token=deterministic_token(index),
            )

        return run

    results = []
    scored_indices: list[int] = []
    ambiguities: Counter[str] = Counter()
    coverage: Counter[str] = Counter()
    for index, (case, projection, record) in enumerate(
        zip(cases, projections, records)
    ):
        if projection.draft is None:
            ambiguities["projection_refused"] += 1
            continue
        entry = migrated[index]
        payload = projection.draft.model_dump(mode="json", warnings="none")
        try:
            results.append(
                run_shadow_context(
                    draft_payload=payload,
                    augmentation=entry.augmentation,
                    run=_run_index(
                        index, derived_authority_ids(entry.augmentation)
                    ),
                    problem_text=projection.problem_text,
                    original_v1_archive_sha256=inventory.archive_sha256,
                    context_index=index,
                )
            )
        except Exception as exc:  # only the type reaches the artifact
            ambiguities[type(exc).__name__] += 1
            continue
        scored_indices.append(index)
        for name, count in entry.augmentation.carrier_counts():
            if count:
                coverage[name] += 1

    assert_no_unaugmented_movement(results)
    if not args.record_regressions:
        assert_no_regression(results)

    snapshot = freeze_runtime_snapshot(
        results,
        original_v1_archive_sha256=inventory.archive_sha256,
        augmentation_manifest_sha256=manifest.digest,
        candidate_archive_sha256=candidate_sha,
        exact_code_head=args.exact_code_head,
        unresolved_augmentation_count=sum(
            1 for item in migrated if item.review_status is ReviewStatus.unresolved
        ),
        migration_ambiguities=tuple(sorted(ambiguities.items())),
    )

    snapshot_payload = snapshot.model_dump(mode="json")
    # The handles pair a runtime record to its gold case inside the scorer and
    # have no business in an artifact, so they leave before anything is written.
    published_snapshot = dict(snapshot_payload)
    published_snapshot["records"] = [
        {key: value for key, value in row.items() if key != "scoring_handle"}
        for row in snapshot_payload["records"]
    ]
    assert_privacy_safe_artifact(published_snapshot)
    args.runtime_snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot_body = (
        json.dumps(published_snapshot, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    )
    args.runtime_snapshot.write_text(snapshot_body, encoding="utf-8")

    # --- PHASE G: the gold opens here, and the pipeline is already closed ---
    gold_by_handle = build_gold_index(
        cases,
        scored_indices,
        original_v1_archive_sha256=inventory.archive_sha256,
    )
    scored = score_shadow_snapshot(snapshot, gold_by_handle)
    score_totals = totals(scored)

    scorecard = build_scored_shadow_scorecard(
        scored,
        score_totals,
        snapshot=snapshot,
        carrier_coverage=tuple(sorted(coverage.items())),
    )
    payload = scored_scorecard_as_dict(scorecard)
    assert_privacy_safe_artifact(payload)
    assert_scores_are_separated({"observed_public_score": "41/81"}, payload)

    args.shadow_report.parent.mkdir(parents=True, exist_ok=True)
    report_body = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    args.shadow_report.write_text(report_body, encoding="utf-8")

    print(f"STAGE7_V2_SHADOW_SCORE_CLASS={payload['score_class']}")
    print("STAGE7_V2_SHADOW_IS_OFFICIAL_SCORE=false")
    print(f"STAGE7_V2_SHADOW_ORIGINAL_V1_ARCHIVE_SHA256={inventory.archive_sha256}")
    print(f"STAGE7_V2_SHADOW_MANIFEST_SHA256={manifest.digest}")
    print(f"STAGE7_V2_SHADOW_CANDIDATE_ARCHIVE_SHA256={candidate_sha}")
    print(
        "STAGE7_V2_SHADOW_CANDIDATE_FILE_SHA256="
        + hashlib.sha256(candidate_body.encode("utf-8")).hexdigest()
    )
    print(f"STAGE7_V2_SHADOW_RUNTIME_SNAPSHOT_SHA256={snapshot.runtime_snapshot_digest}")
    print(
        "STAGE7_V2_SHADOW_RUNTIME_SNAPSHOT_FILE_SHA256="
        + hashlib.sha256(snapshot_body.encode("utf-8")).hexdigest()
    )
    print(
        "STAGE7_V2_SHADOW_REPORT_FILE_SHA256="
        + hashlib.sha256(report_body.encode("utf-8")).hexdigest()
    )
    print(f"STAGE7_V2_SHADOW_DIGEST={scorecard.digest}")
    print(f"STAGE7_V2_SHADOW_CONTEXTS={scorecard.context_count}")
    print(f"STAGE7_V2_SHADOW_AUGMENTED={scorecard.augmented_context_count}")
    print(f"STAGE7_V2_SHADOW_UNRESOLVED={scorecard.unresolved_augmentation_count}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED={scorecard.newly_solved}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_CORRECT={scorecard.newly_solved_correct}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_WRONG={scorecard.newly_solved_wrong}")
    print(f"STAGE7_V2_SHADOW_NEWLY_SOLVED_UNSCORED={scorecard.newly_solved_unscored}")
    print(f"STAGE7_V2_SHADOW_ALL_CORRECT={scorecard.all_shadow_correct}")
    print(f"STAGE7_V2_SHADOW_ALL_WRONG={scorecard.all_shadow_wrong}")
    print(f"STAGE7_V2_SHADOW_ALL_UNSCORED={scorecard.all_shadow_unscored}")
    print(f"STAGE7_V2_SHADOW_FORBIDDEN_CLASS_SOLVE={scorecard.forbidden_class_solve}")
    print(f"STAGE7_V2_SHADOW_REGRESSED={scorecard.regressed}")
    if scorecard.regressed:
        print(
            "STAGE7_V2_SHADOW_NOTE=a carrier took a solve away; this candidate "
            "is not ready to be projected"
        )
    print(f"STAGE7_V2_SHADOW_COHORT_YIELD={scorecard.cohort_yield_count}")
    for name, count in scorecard.carrier_coverage:
        print(f"STAGE7_V2_SHADOW_CARRIER_{name}={count}")
    for name, count in scorecard.scoring_defect_counts:
        print(f"STAGE7_V2_SHADOW_DEFECT_{name}={count}")
    for name, count in scorecard.migration_ambiguities:
        print(f"STAGE7_V2_SHADOW_AMBIGUITY_{name}={count}")
    failures = scorecard.acceptance_failures
    print(
        "STAGE7_V2_SHADOW_ACCEPTANCE="
        + ("PASS" if not failures else "FAIL:" + ",".join(failures))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
