"""Build the distinct Phase 56 Stage 7 supplemental yield manifest.

The command reads the approved public archive but neither runs the product nor
scores a result.  Its output must be outside the repository.  An existing
byte-identical manifest is verified in place; a different existing file is
refused rather than overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.corpus_integrity import (  # noqa: E402
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import load_public_cases  # noqa: E402
from evaluation.phase56_stage7.corpus_v2.supplemental_campaign import (  # noqa: E402
    EXPECTED_SELECTED_CONTEXTS,
    SUPPLEMENTAL_CAMPAIGN_ID,
    SupplementalManifestRefused,
    build_supplemental_manifest,
    supplemental_manifest_body,
)


REFUSAL_EXIT = 2


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _publish_new_or_verify(path: Path, body: str) -> str:
    resolved = path.resolve()
    if _is_within(resolved, REPOSITORY_ROOT.resolve()):
        raise ValueError("supplemental_manifest_output_inside_repository")
    if not resolved.parent.is_dir():
        raise ValueError("supplemental_manifest_output_parent_missing")

    encoded = body.encode("utf-8")
    if resolved.exists():
        if resolved.read_bytes() != encoded:
            raise ValueError("supplemental_manifest_existing_output_differs")
        return "VERIFIED_EXISTING"

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=resolved.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, resolved)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return "CREATED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        inventory = read_public_corpus_archive(args.corpus_archive)
        public_dev, public_adversarial = load_public_cases(inventory)
        built = build_supplemental_manifest((*public_dev, *public_adversarial))
        body = supplemental_manifest_body(built.manifest)
        disposition = _publish_new_or_verify(args.output, body)
    except SupplementalManifestRefused as exc:
        print(f"STAGE7_SUPPLEMENTAL_MANIFEST=FAIL:{exc.reason.value}", file=sys.stderr)
        return REFUSAL_EXIT
    except Exception as exc:
        # Only a closed tool-owned reason or the exception type leaves.  Corpus
        # text and record identities stay in the restricted process.
        reason = str(exc)
        if not reason.startswith("supplemental_manifest_"):
            reason = type(exc).__name__
        print(f"STAGE7_SUPPLEMENTAL_MANIFEST=FAIL:{reason}", file=sys.stderr)
        return REFUSAL_EXIT

    file_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    print(f"STAGE7_SUPPLEMENTAL_CAMPAIGN_ID={SUPPLEMENTAL_CAMPAIGN_ID}")
    print(f"STAGE7_SUPPLEMENTAL_MANIFEST_DISPOSITION={disposition}")
    print(f"STAGE7_SUPPLEMENTAL_MANIFEST_ENTRY_COUNT={len(built.manifest.entries)}")
    print(f"STAGE7_SUPPLEMENTAL_SELECTED_CONTEXTS={EXPECTED_SELECTED_CONTEXTS}")
    for cohort, positions in built.selection.by_cohort:
        print(f"STAGE7_SUPPLEMENTAL_COHORT_{cohort.value.upper()}={len(positions)}")
    print(f"STAGE7_SUPPLEMENTAL_SELECTION_DIGEST={built.selection_identity_digest}")
    print(f"STAGE7_SUPPLEMENTAL_MANIFEST_DIGEST={built.manifest.digest}")
    print(f"STAGE7_SUPPLEMENTAL_MANIFEST_FILE_SHA256={file_sha}")
    print("STAGE7_SUPPLEMENTAL_MANIFEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
