"""Trace source semantics through the pipeline against the authorised archive.

The audit itself is a pure function over one source record and its projected
Draft.  This runner supplies both from the public archive, normalises each Draft
to an IR where the engine accepts it, and writes the aggregate.

Only gold *structure* is read — entities, segments, events, facts, relations,
assumptions and queries.  The answer block is never opened, and the written
artifact carries no case identifier, family, problem text, evidence quote, or
numeric value from a source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.authority_census import (  # noqa: E402
    available_carriers,
    required_carriers,
)
from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import (  # noqa: E402
    load_public_cases,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (  # noqa: E402
    project_case_to_draft,
)
from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)
from evaluation.phase56_stage7.semantic_preservation import (  # noqa: E402
    EngineCarrier,
    build_carrier_omissions,
    build_semantic_preservation_report,
    report_as_dict,
    trace_context,
)

# The census carrier vocabulary and the audit carrier vocabulary overlap but are
# not the same enum — the audit asks a question about the *contract* and the
# census asks one about a context.  Mapped explicitly so neither is silently
# reinterpreted as the other.
_CENSUS_TO_AUDIT: dict[str, EngineCarrier] = {
    "reference_frame": EngineCarrier.reference_frame,
    "angle_reference_datum": EngineCarrier.angle_reference_datum,
    "motion_sense": EngineCarrier.motion_sense,
    "contact_side": EngineCarrier.contact_side,
    "endpoint_condition": EngineCarrier.endpoint_condition,
    "constraint_authority": EngineCarrier.constraint_record,
    "interaction_target": EngineCarrier.interaction_participant,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inventory = read_public_corpus_archive(args.corpus_archive)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    traces = []
    rejected = 0
    requiring: Counter[EngineCarrier] = Counter()
    supplying: Counter[EngineCarrier] = Counter()
    for case in cases:
        projection = project_case_to_draft(case)
        draft = projection.draft
        if draft is None:
            # A refused projection is not a semantic loss.  Counted on its own
            # line rather than folded into the field trace, where it would have
            # reported every field of that context as dropped.
            rejected += 1
            continue
        traces.append(trace_context(case.gold, draft))
        for item in required_carriers(draft):
            mapped = _CENSUS_TO_AUDIT.get(item.value)
            if mapped is not None:
                requiring[mapped] += 1
        for item in available_carriers(draft):
            mapped = _CENSUS_TO_AUDIT.get(item.value)
            if mapped is not None:
                supplying[mapped] += 1

    report = build_semantic_preservation_report(
        traces,
        carriers=build_carrier_omissions(requiring=requiring, supplying=supplying),
    )
    payload = report_as_dict(report)
    payload["corpus_zip_sha256"] = inventory.archive_sha256
    payload["rejected_projection_count"] = rejected
    assert_privacy_safe_artifact(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.write_text(body, encoding="utf-8")

    print(f"STAGE7_SEMANTIC_AUDIT_REPORT={args.output}")
    print(f"STAGE7_SEMANTIC_AUDIT_DIGEST={report.digest}")
    print(
        "STAGE7_SEMANTIC_AUDIT_FILE_SHA256="
        + hashlib.sha256(body.encode("utf-8")).hexdigest()
    )
    print(f"STAGE7_SEMANTIC_AUDIT_CONTEXTS={report.context_count}")
    print(f"STAGE7_SEMANTIC_AUDIT_REJECTED_PROJECTIONS={rejected}")
    print(f"STAGE7_SEMANTIC_AUDIT_FIELDS={len(report.fields)}")
    print(
        "STAGE7_SEMANTIC_AUDIT_SOURCE_OMISSIONS="
        + str(report.source_contract_omission_count)
    )
    print(f"STAGE7_SEMANTIC_AUDIT_PROJECTION_LOSS={report.projection_loss_count}")
    print(
        "STAGE7_SEMANTIC_AUDIT_NORMALIZATION_LOSS="
        + str(report.normalization_loss_count)
    )
    print(
        "STAGE7_SEMANTIC_AUDIT_LAW_CONSUMPTION_GAPS="
        + str(report.law_consumption_gap_count)
    )
    for name, count in report.status_counts:
        print(f"STAGE7_SEMANTIC_AUDIT_STATUS_{name}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
