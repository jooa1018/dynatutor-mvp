"""Produce the executable authority census against the authorised public archive.

The census itself lives in `evaluation.phase56_stage7.authority_census` and is a
pure function over projected Drafts and lane results.  This runner is the part
that has to touch the corpus: it reads the authorised archive, projects every
public case, runs the real Lane B pipeline, joins each context with its expected
class, and writes the aggregate.

Order is the same discipline the strict gate uses and is enforced by
construction: every runtime result is produced first, from the runtime domain
only, and the expected classes are read afterwards.  The runtime never sees an
expected terminal.

The written artifact is privacy-safe by construction — the census records have
no field that could hold a case identifier, a family, problem text, an expected
answer, or a source numeric — and `assert_privacy_safe_artifact` is run over it
before the file is written, so a regression fails closed rather than leaking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.authority_census import (  # noqa: E402
    ExpectedClass,
    build_authority_census,
    build_authority_context,
    census_as_dict,
)
from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import (  # noqa: E402
    load_public_cases,
)
from evaluation.phase56_stage7.corpus_semantics import (  # noqa: E402
    scope_adjusted_expected_terminal,
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

# The corpus states an expected terminal per case; the census only ever needs
# its *class*.  Mapping here, in the runner, keeps the census module itself free
# of any gold vocabulary.
_EXPECTED_CLASS_BY_TERMINAL: dict[str, ExpectedClass] = {
    "accepted": ExpectedClass.supported,
    "deferred_unsupported": ExpectedClass.deferred,
    "unsupported_other": ExpectedClass.unsupported_other,
    "needs_figure": ExpectedClass.needs_figure,
    "needs_confirmation": ExpectedClass.needs_confirmation,
    "insufficient_information": ExpectedClass.insufficient_information,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-archive",
        type=Path,
        required=True,
        help="authorised public corpus zip, outside the repository",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="out-of-repository destination for the census aggregate",
    )
    args = parser.parse_args()

    inventory = read_public_corpus_archive(args.corpus_archive)
    public_dev, public_adversarial = load_public_cases(inventory)
    cases = (*public_dev, *public_adversarial)

    # --- runtime first, with no gold member in scope -----------------------
    projections = [project_case_to_draft(case) for case in cases]
    results = [
        run_lane_b_case(projection, execution_token=deterministic_token(index))
        for index, projection in enumerate(projections)
    ]

    # --- the runtime record is now complete; expected classes may be read --
    # The scorer's own scope-adjusted derivation is reused rather than reread:
    # a census that classified cases differently from the gate would partition
    # a different population and quietly disagree with the score it explains.
    rows = []
    for index, (case, projection, result) in enumerate(
        zip(cases, projections, results, strict=True)
    ):
        expected_terminal = scope_adjusted_expected_terminal(case, case_index=index)
        expected = _EXPECTED_CLASS_BY_TERMINAL.get(
            expected_terminal.value, ExpectedClass.unknown
        )
        rows.append(
            build_authority_context(
                projection.draft, result, expected_class=expected
            )
        )

    census = build_authority_census(rows)
    payload = census_as_dict(census)
    payload["corpus_zip_sha256"] = inventory.archive_sha256
    assert_privacy_safe_artifact(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.write_text(body, encoding="utf-8")

    print(f"STAGE7_CENSUS_REPORT={args.output}")
    print(f"STAGE7_CENSUS_DIGEST={census.digest}")
    print(
        "STAGE7_CENSUS_FILE_SHA256="
        + hashlib.sha256(body.encode("utf-8")).hexdigest()
    )
    print(f"STAGE7_CENSUS_CONTEXTS={census.context_count}")
    print(f"STAGE7_CENSUS_SUPPORTED_UNSOLVED={census.supported_unsolved}")
    print(f"STAGE7_CENSUS_COHORTS={census.cohort_count}")
    print(
        "STAGE7_CENSUS_SUPPORTED_UNSOLVED_COHORTS="
        + str(census.supported_unsolved_cohort_count)
    )
    print(f"STAGE7_CENSUS_CLOSURE_CANDIDATES={census.closure_candidate_count}")
    print(f"STAGE7_CENSUS_AUTHORITY_BLOCKED={census.authority_blocked_count}")
    print(
        "STAGE7_CENSUS_REFERENCE_FRAME_DEPENDENT="
        + str(census.reference_frame_dependent_count)
    )
    print(
        "STAGE7_CENSUS_REFERENCE_FRAME_COHORTS="
        + str(census.reference_frame_dependent_cohort_count)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
