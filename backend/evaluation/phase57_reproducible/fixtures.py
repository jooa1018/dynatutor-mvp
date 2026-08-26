"""Validate and materialize the repository-contained Phase 57 public inputs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.phase56_stage7.corpus_records import (
    PublicCorpusCaseV1,
    parse_public_jsonl,
    parse_schema_document,
)
from evaluation.phase56_stage7.corpus_v2.supplemental_campaign import (
    build_supplemental_manifest,
    supplemental_manifest_body,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase57_reproducible.contracts import (
    PHASE57_CONTINUATION_MANIFEST_DIGEST,
    PHASE57_CONTINUATION_MANIFEST_FILE_SHA256,
    PHASE57_CONTINUATION_SELECTION_DIGEST,
    PHASE57_FIXTURE_SET_DIGEST,
    PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    PHASE57_SOURCE_PUBLIC_ARCHIVE_SHA256,
)


PHASE57_FIXTURE_SCHEMA = "dynatutor.phase57.reproducible_public_fixture_set.v1"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_ROOT = _BACKEND_ROOT / "tests/fixtures/phase56_stage7_public"

_ARCHIVE_MEMBER_NAMES: tuple[str, ...] = (
    "public_adversarial.jsonl",
    "public_dev.jsonl",
    "schema.json",
)
_ALLOWED_FIXTURE_NAMES: frozenset[str] = frozenset(
    (*_ARCHIVE_MEMBER_NAMES, "README.md", "sanitized_manifest.json")
)

_MEMBER_CONTRACT: dict[str, dict[str, Any]] = {
    "public_adversarial.jsonl": {
        "bytes": 44_322,
        "count": 16,
        "sha256": "d3d424b1218ba58fed89778a25d1f5baf97edee5493f0465f37cd0acf18b39b7",
    },
    "public_dev.jsonl": {
        "bytes": 287_936,
        "count": 84,
        "sha256": "f06606670b0206d0900ecb136378c0b81cb30e2f62a1519cea4d83ed5f05c4f8",
    },
    "schema.json": {
        "bytes": 3_996,
        "count": None,
        "sha256": "cd2e0dbe39d73989c62f868a4e4a0e750692987e27feb36405521b35f60b1673",
    },
}


class Phase57FixtureRefused(RuntimeError):
    """A privacy-safe, content-free fixture identity refusal."""


@dataclass(frozen=True, slots=True)
class Phase57CampaignInputsV1:
    fixture_root: Path
    corpus_archive: Path
    manifest: Path
    fixture_set_digest: str
    corpus_archive_sha256: str
    manifest_digest: str
    manifest_file_sha256: str
    selection_identity_digest: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(raw)


def expected_sanitized_manifest() -> dict[str, Any]:
    return {
        "schema": PHASE57_FIXTURE_SCHEMA,
        "source_archive_sha256": PHASE57_SOURCE_PUBLIC_ARCHIVE_SHA256,
        "public_case_count": 100,
        "contains_private_heldout": False,
        "contains_public_all": False,
        "members": [
            {
                "name": name,
                "count": _MEMBER_CONTRACT[name]["count"],
                "bytes": _MEMBER_CONTRACT[name]["bytes"],
                "sha256": _MEMBER_CONTRACT[name]["sha256"],
            }
            for name in _ARCHIVE_MEMBER_NAMES
        ],
    }


def validate_fixture_set(fixture_root: Path = DEFAULT_FIXTURE_ROOT) -> None:
    """Require the exact public-only files and byte identities."""

    try:
        observed_items = tuple(fixture_root.iterdir())
    except OSError as exc:
        raise Phase57FixtureRefused("fixture_root_unreadable") from exc
    observed_names = frozenset(item.name for item in observed_items)
    if observed_names != _ALLOWED_FIXTURE_NAMES:
        raise Phase57FixtureRefused("fixture_member_set_mismatch")
    if any(item.is_symlink() or not item.is_file() for item in observed_items):
        raise Phase57FixtureRefused("fixture_member_not_regular")

    for name, expected in _MEMBER_CONTRACT.items():
        path = fixture_root / name
        if path.is_symlink() or not path.is_file():
            raise Phase57FixtureRefused("fixture_member_not_regular")
        data = path.read_bytes()
        if len(data) != expected["bytes"]:
            raise Phase57FixtureRefused("fixture_member_byte_count_mismatch")
        if _sha256(data) != expected["sha256"]:
            raise Phase57FixtureRefused("fixture_member_sha256_mismatch")
        expected_count = expected["count"]
        if expected_count is not None:
            count = sum(1 for line in data.splitlines() if line.strip())
            if count != expected_count:
                raise Phase57FixtureRefused("fixture_member_record_count_mismatch")

    manifest_path = fixture_root / "sanitized_manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest_payload = json.loads(manifest_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase57FixtureRefused("sanitized_manifest_unreadable") from exc
    expected_manifest = expected_sanitized_manifest()
    expected_manifest_raw = (
        json.dumps(
            expected_manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    if manifest_raw != expected_manifest_raw or manifest_payload != expected_manifest:
        raise Phase57FixtureRefused("sanitized_manifest_content_mismatch")
    if _canonical_digest(manifest_payload) != PHASE57_FIXTURE_SET_DIGEST:
        raise Phase57FixtureRefused("fixture_set_digest_mismatch")


def load_public_fixture_cases(
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> tuple[PublicCorpusCaseV1, ...]:
    """Parse all 100 public cases after exact fixture validation."""

    validate_fixture_set(fixture_root)
    declared_schema = parse_schema_document((fixture_root / "schema.json").read_bytes())
    public_dev = parse_public_jsonl(
        (fixture_root / "public_dev.jsonl").read_bytes(),
        split=PublicSplit.public_dev,
        declared_schema=declared_schema,
    )
    public_adversarial = parse_public_jsonl(
        (fixture_root / "public_adversarial.jsonl").read_bytes(),
        split=PublicSplit.public_adversarial,
        declared_schema=declared_schema,
    )
    cases = (*public_dev, *public_adversarial)
    if len(cases) != 100:
        raise Phase57FixtureRefused("public_fixture_population_mismatch")
    return cases


def build_reproducible_archive_bytes(
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> bytes:
    """Create platform-independent ZIP_STORED bytes from the three public inputs."""

    validate_fixture_set(fixture_root)
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_STORED,
        allowZip64=False,
    ) as archive:
        for name in _ARCHIVE_MEMBER_NAMES:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits = 0
            info.extra = b""
            info.comment = b""
            archive.writestr(info, (fixture_root / name).read_bytes())
    raw = output.getvalue()
    if _sha256(raw) != PHASE57_REPRODUCIBLE_ARCHIVE_SHA256:
        raise Phase57FixtureRefused("reproducible_archive_sha256_mismatch")
    return raw


def build_continuation_manifest(
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> tuple[str, str, str]:
    """Return manifest body, canonical digest, and source-only selection digest."""

    built = build_supplemental_manifest(load_public_fixture_cases(fixture_root))
    body = supplemental_manifest_body(built.manifest)
    if built.manifest.digest != PHASE57_CONTINUATION_MANIFEST_DIGEST:
        raise Phase57FixtureRefused("continuation_manifest_digest_mismatch")
    if _sha256(body.encode("utf-8")) != PHASE57_CONTINUATION_MANIFEST_FILE_SHA256:
        raise Phase57FixtureRefused("continuation_manifest_file_sha256_mismatch")
    if built.selection_identity_digest != PHASE57_CONTINUATION_SELECTION_DIGEST:
        raise Phase57FixtureRefused("continuation_selection_digest_mismatch")
    return body, built.manifest.digest, built.selection_identity_digest


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def materialize_campaign_inputs(
    output_root: Path,
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> Phase57CampaignInputsV1:
    """Write deterministic campaign inputs outside the repository worktree."""

    output_root.mkdir(parents=True, exist_ok=True)
    corpus_archive = output_root / "phase57-public-fixtures.zip"
    manifest = output_root / "phase57-continuation-manifest.json"
    archive_bytes = build_reproducible_archive_bytes(fixture_root)
    manifest_body, manifest_digest, selection_digest = build_continuation_manifest(
        fixture_root
    )
    _write_bytes_atomic(corpus_archive, archive_bytes)
    _write_bytes_atomic(manifest, manifest_body.encode("utf-8"))
    return Phase57CampaignInputsV1(
        fixture_root=fixture_root,
        corpus_archive=corpus_archive,
        manifest=manifest,
        fixture_set_digest=PHASE57_FIXTURE_SET_DIGEST,
        corpus_archive_sha256=_sha256(archive_bytes),
        manifest_digest=manifest_digest,
        manifest_file_sha256=_sha256(manifest_body.encode("utf-8")),
        selection_identity_digest=selection_digest,
    )


__all__ = [
    "DEFAULT_FIXTURE_ROOT",
    "PHASE57_FIXTURE_SCHEMA",
    "Phase57CampaignInputsV1",
    "Phase57FixtureRefused",
    "build_continuation_manifest",
    "build_reproducible_archive_bytes",
    "expected_sanitized_manifest",
    "load_public_fixture_cases",
    "materialize_campaign_inputs",
    "validate_fixture_set",
]
