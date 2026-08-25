"""Pre-upload identity and integrity check for the Stage 7 CI artifact.

A green Stage 7 workflow and a trustworthy Stage 7 artifact are different
claims.  The workflow's own conclusion says the steps exited zero; it says
nothing about *which source* the file that leaves the runner describes.  Those
came apart once already: the gate recorded ``GITHUB_SHA``, which on a
``pull_request`` event is the ephemeral ``refs/pull/<n>/merge`` commit, so runs
that checked out and tested one commit uploaded a report naming a different
one — a commit unreachable from any branch, which no auditor can resolve.

This checker runs immediately before ``upload-artifact`` and refuses the upload
unless the artifact is evidence about the source that was actually checked out:

    configured expected head == git rev-parse HEAD == report exact_head_sha

and unless the bytes on disk are still the bytes the gate sealed when it wrote
them.  Every check fails closed and reports the name of the gate it hit, so a
refusal says which property was violated rather than only that something was
wrong.

It parses the report structurally.  A grep would accept a SHA that appears
anywhere in the file, including inside an unrelated string.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.redaction import (  # noqa: E402
    assert_privacy_safe_artifact,
)

# Exactly forty lowercase hex characters, anchored.  Uppercase, abbreviated and
# whitespace-padded spellings are refused rather than normalised: the artifact
# is compared byte-for-byte against other records, so one commit must have one
# spelling here.
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
RAW_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")

EXPECTED_SCHEMA = "dynatutor.phase56_stage7.offline_gate"
EXPECTED_VERSION = "1.0"

# Fields the aggregate must carry for a reader to know what the run was and
# what it measured.  A report missing any of them is not a Stage 7 artifact.
REQUIRED_TOP_LEVEL_FIELDS = (
    "schema",
    "version",
    "evaluator_version",
    "contract_version",
    "exact_head_sha",
    "gates",
    "public_corpus",
    "lane_b",
    "external_model_calls",
    "private_heldout_accesses",
)

# Lanes that cannot have run without the authorised public archive.  A
# corpus-independent run reports them NOT_RUN; a report that claims one of them
# PASS while declaring no corpus is the exact misreading this gate exists to
# stop, so it is refused here rather than corrected downstream.
PUBLIC_CORPUS_DEPENDENT_LANES = (
    "lane_b",
    "lane_c",
    "lane_d",
    "lane_e",
    "compositional_12",
    "synthetic_38",
    "metamorphic",
    "physics_changing_controls",
    "hard_safety",
)


class IdentityFailure(Exception):
    """A named refusal.  ``code`` is the gate that refused."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _checkout_head_sha(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise IdentityFailure("checkout_head_sha_unavailable", str(exc)) from exc
    head = completed.stdout.strip().casefold()
    if not GIT_SHA_PATTERN.fullmatch(head):
        raise IdentityFailure("checkout_head_sha_malformed", repr(head))
    return head


def _read_raw_bytes(report_path: Path) -> bytes:
    if not report_path.is_file():
        raise IdentityFailure("artifact_report_missing", str(report_path))
    try:
        return report_path.read_bytes()
    except OSError as exc:
        raise IdentityFailure("artifact_report_unreadable", str(exc)) from exc


def _parse_report(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityFailure("artifact_report_malformed_json", str(exc)) from exc
    if not isinstance(document, dict):
        raise IdentityFailure(
            "artifact_report_not_an_object", type(document).__name__
        )
    return document


def _report_exact_head_sha(document: dict[str, Any]) -> str:
    if "exact_head_sha" not in document:
        raise IdentityFailure("artifact_report_exact_head_sha_missing")
    value = document["exact_head_sha"]
    if not isinstance(value, str):
        raise IdentityFailure(
            "artifact_report_exact_head_sha_malformed", type(value).__name__
        )
    # Compared as written.  Stripping or lowering here would accept a padded or
    # uppercase spelling and then report the tidied value, which is a different
    # string from the one the file actually contains.
    if not GIT_SHA_PATTERN.fullmatch(value):
        raise IdentityFailure("artifact_report_exact_head_sha_malformed", repr(value))
    return value


def _check_schema(document: dict[str, Any]) -> None:
    missing = [name for name in REQUIRED_TOP_LEVEL_FIELDS if name not in document]
    if missing:
        raise IdentityFailure(
            "artifact_report_schema_incomplete", ",".join(sorted(missing))
        )
    if document["schema"] != EXPECTED_SCHEMA:
        raise IdentityFailure(
            "artifact_report_schema_unexpected", repr(document["schema"])
        )
    if document["version"] != EXPECTED_VERSION:
        raise IdentityFailure(
            "artifact_report_version_unexpected", repr(document["version"])
        )
    gates = document["gates"]
    if not isinstance(gates, list) or not gates:
        raise IdentityFailure("artifact_report_gates_missing")
    for gate in gates:
        if not isinstance(gate, dict) or "name" not in gate or "result" not in gate:
            raise IdentityFailure("artifact_report_gate_entry_malformed", repr(gate))


def _check_privacy_contract(document: dict[str, Any]) -> None:
    try:
        assert_privacy_safe_artifact(document)
    except ValueError as exc:
        raise IdentityFailure("artifact_report_privacy_unsafe", str(exc)) from exc
    for name, expected in (
        ("external_model_calls", 0),
        ("private_heldout_accesses", 0),
    ):
        if document.get(name) != expected:
            raise IdentityFailure(
                "artifact_report_offline_claim_violated",
                f"{name}={document.get(name)!r}",
            )


def _check_public_corpus_scope(document: dict[str, Any]) -> None:
    """A run without the archive must not read back as a public-100 pass."""

    corpus = document.get("public_corpus")
    if not isinstance(corpus, dict):
        raise IdentityFailure("artifact_report_public_corpus_section_missing")
    supplied = corpus.get("supplied")
    if supplied:
        return
    for lane in PUBLIC_CORPUS_DEPENDENT_LANES:
        section = document.get(lane)
        if not isinstance(section, dict):
            continue
        for field in ("result", "disposition"):
            if section.get(field) == "PASS":
                raise IdentityFailure(
                    "artifact_report_corpus_independent_claims_public_pass",
                    f"{lane}.{field}",
                )


def _check_raw_digest(raw: bytes, expected_digest: str) -> str:
    # Surrounding whitespace is tolerated because the value arrives through a
    # shell capture; the spelling itself is not normalised.  An uppercase or
    # abbreviated digest is a caller defect, and quietly repairing it would
    # hide the defect behind a passing check.
    expected = expected_digest.strip()
    if not RAW_DIGEST_PATTERN.fullmatch(expected):
        raise IdentityFailure(
            "artifact_expected_raw_sha256_malformed", repr(expected_digest)
        )
    # Hashed from the raw bytes, never from a decoded string: a text-mode read
    # would fold CRLF to LF and let two different files seal to one digest.
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise IdentityFailure(
            "artifact_report_raw_digest_mismatch", f"{actual} != {expected}"
        )
    return actual


def check_artifact_identity(
    *,
    report_path: Path,
    expected_head_sha: str,
    expected_raw_sha256: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, str]:
    """Return the audited identity, or raise the first :class:`IdentityFailure`."""

    expected_head = expected_head_sha.strip()
    if not GIT_SHA_PATTERN.fullmatch(expected_head):
        raise IdentityFailure(
            "expected_head_sha_malformed", repr(expected_head_sha)
        )

    checkout_head = _checkout_head_sha(repository_root)
    if checkout_head != expected_head:
        raise IdentityFailure(
            "checkout_head_sha_mismatch", f"{checkout_head} != {expected_head}"
        )

    raw = _read_raw_bytes(report_path)
    digest = _check_raw_digest(raw, expected_raw_sha256)
    document = _parse_report(raw)
    _check_schema(document)

    report_head = _report_exact_head_sha(document)
    if report_head != checkout_head:
        raise IdentityFailure(
            "artifact_report_exact_head_sha_mismatch",
            f"{report_head} != {checkout_head}",
        )

    _check_privacy_contract(document)
    _check_public_corpus_scope(document)

    return {
        "expected_head_sha": expected_head,
        "checkout_head_sha": checkout_head,
        "report_exact_head_sha": report_head,
        "report_raw_sha256": digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=Path, required=True, help="the report about to be uploaded"
    )
    parser.add_argument(
        "--expect-head-sha",
        required=True,
        help="the head the workflow configured and checked out",
    )
    parser.add_argument(
        "--expect-raw-sha256",
        required=True,
        help="the raw SHA-256 the gate sealed when it wrote the report",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="worktree whose HEAD the report must describe",
    )
    args = parser.parse_args(argv)

    try:
        identity = check_artifact_identity(
            report_path=args.report,
            expected_head_sha=args.expect_head_sha,
            expected_raw_sha256=args.expect_raw_sha256,
            repository_root=args.repository_root,
        )
    except IdentityFailure as failure:
        print(f"STAGE7_ARTIFACT_IDENTITY_DETAIL={failure.detail}")
        print("STAGE7_ARTIFACT_IDENTITY_MATCH=false")
        print(f"STAGE7_CI_ARTIFACT_IDENTITY=FAIL:{failure.code}")
        return 2

    print(f"EXPECTED_HEAD_SHA={identity['expected_head_sha']}")
    print(f"CHECKOUT_HEAD_SHA={identity['checkout_head_sha']}")
    print(f"REPORT_EXACT_HEAD_SHA={identity['report_exact_head_sha']}")
    print(f"REPORT_RAW_SHA256={identity['report_raw_sha256']}")
    print("STAGE7_ARTIFACT_IDENTITY_MATCH=true")
    print("STAGE7_CI_ARTIFACT_IDENTITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
