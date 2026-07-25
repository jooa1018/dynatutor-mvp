"""Stage 7 public corpus archive integrity and safe in-memory extraction.

This module is deliberately free of engine, app, solver, compiler, and provider
imports.  Every failure it raises happens before any runtime execution, so an
integrity failure always terminates with zero runtime/compiler/solver/provider
calls and zero cost.

The archive is never written to disk and ``extract``/``extractall`` is never
called, so no archive member can ever materialise a link, a device node, or a
traversed path on the evaluator filesystem.
"""

from __future__ import annotations

import hashlib
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

from evaluation.phase56_stage7.contracts import (
    PUBLIC_CORPUS_ZIP_SHA256,
    Stage7FailureKind,
    stage7_evaluation_contract,
)


ARCHIVE_POLICY_VERSION = "phase56-stage7-archive-integrity-v1"

# The ZIP local-file-header magic.  Empty and spanned archives are rejected: the
# authorised corpus always carries at least the two public splits.
_ZIP_LOCAL_HEADER_MAGIC = b"PK\x03\x04"

MAX_ARCHIVE_FILE_BYTES = 10_000_000
MAX_ARCHIVE_ENTRY_COUNT = 32
MAX_ENTRY_NAME_LENGTH = 128
MAX_COMPRESSION_RATIO = 200.0

REQUIRED_ARCHIVE_MEMBERS: tuple[str, ...] = (
    "public_dev.jsonl",
    "public_adversarial.jsonl",
    "schema.json",
)
OPTIONAL_READABLE_ARCHIVE_MEMBERS: tuple[str, ...] = (
    "manifest.json",
    "validation_report.json",
    "corpus_summary.json",
    "taxonomy.json",
    "coverage_map.md",
    "preview.md",
    "README.md",
    "LICENSE",
    "LICENSE.txt",
)
# Present-allowed but never parsed for content.  ``public_all.jsonl`` is a
# superset view the Stage 7 contract does not authorise, and the private
# manifest is only ever inspected keys-only by :mod:`corpus_semantics`.
QUARANTINED_ARCHIVE_MEMBERS: tuple[str, ...] = (
    "public_all.jsonl",
    "private_heldout_manifest_without_text.json",
)
PRIVATE_MANIFEST_MEMBER = "private_heldout_manifest_without_text.json"
FORBIDDEN_ARCHIVE_MEMBERS: tuple[str, ...] = (
    "DO_NOT_SHARE_WITH_CODEX_private_heldout.jsonl",
    "all_cases.jsonl",
    "dynatutor_beer12_ko_corpus_v1_full.zip",
)

_NESTED_ARCHIVE_PREFIXES: tuple[bytes, ...] = (
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"\x1f\x8b",
    b"BZh",
    b"\xfd7zXZ\x00",
    b"\x28\xb5\x2f\xfd",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"\x04\x22\x4d\x18",
    b"!<arch>\n",
)
_TAR_MAGIC_OFFSET = 257
_TAR_MAGICS: tuple[bytes, ...] = (b"ustar\x0000", b"ustar  \x00")

_ALLOWED_COMPRESSION_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_UNIX_CREATE_SYSTEM = 3
_INFOZIP_UNIX1_EXTRA_ID = 0x000D
_INFOZIP_UNIX1_FIXED_BYTES = 12


class CorpusIntegrityReason(str, Enum):
    """Closed, privacy-safe rejection catalogue.

    Reason values never carry archive content or member-supplied text, so they
    are safe to place in a redacted report artifact.
    """

    archive_missing = "archive_missing"
    archive_not_regular_file = "archive_not_regular_file"
    archive_byte_limit_exceeded = "archive_byte_limit_exceeded"
    archive_magic_mismatch = "archive_magic_mismatch"
    archive_sha256_mismatch = "archive_sha256_mismatch"
    archive_not_readable_zip = "archive_not_readable_zip"
    entry_count_limit_exceeded = "entry_count_limit_exceeded"
    entry_name_length_exceeded = "entry_name_length_exceeded"
    entry_name_not_portable = "entry_name_not_portable"
    absolute_entry_path = "absolute_entry_path"
    parent_traversal_entry_path = "parent_traversal_entry_path"
    drive_or_unc_entry_path = "drive_or_unc_entry_path"
    directory_entry = "directory_entry"
    symlink_entry = "symlink_entry"
    hardlink_entry = "hardlink_entry"
    device_entry = "device_entry"
    duplicate_entry_name = "duplicate_entry_name"
    case_insensitive_duplicate_entry_name = "case_insensitive_duplicate_entry_name"
    unexpected_entry_name = "unexpected_entry_name"
    forbidden_private_entry_name = "forbidden_private_entry_name"
    missing_required_entry = "missing_required_entry"
    encrypted_entry = "encrypted_entry"
    unsupported_compression_method = "unsupported_compression_method"
    entry_size_limit_exceeded = "entry_size_limit_exceeded"
    total_uncompressed_limit_exceeded = "total_uncompressed_limit_exceeded"
    compression_ratio_limit_exceeded = "compression_ratio_limit_exceeded"
    declared_size_mismatch = "declared_size_mismatch"
    entry_checksum_mismatch = "entry_checksum_mismatch"
    nested_archive_entry = "nested_archive_entry"
    entry_not_utf8 = "entry_not_utf8"


class CorpusIntegrityError(Exception):
    """Fail-closed archive rejection carrying no member-supplied content."""

    def __init__(
        self,
        reason: CorpusIntegrityReason,
        *,
        entry_index: int | None = None,
        failure_kind: Stage7FailureKind = Stage7FailureKind.corpus_integrity_failure,
    ) -> None:
        detail = reason.value
        if entry_index is not None:
            detail = f"{detail}[entry:{entry_index}]"
        super().__init__(detail)
        self.reason = reason
        self.entry_index = entry_index
        self.failure_kind = failure_kind

    @property
    def sanitized_reason(self) -> str:
        return str(self)


@dataclass(frozen=True, slots=True)
class ArchiveEntryEvidence:
    """Privacy-safe per-entry evidence: no content, no member-supplied text."""

    index: int
    name: str
    compressed_bytes: int
    uncompressed_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SafeArchiveInventory:
    """In-memory result of a fully validated archive.

    ``members`` holds only the authorised readable entries.  Quarantined member
    content is never exposed here; the private manifest is available solely for
    the keys-only absence audit.
    """

    policy_version: str
    archive_sha256: str
    archive_bytes: int
    entries: tuple[ArchiveEntryEvidence, ...]
    members: Mapping[str, bytes]
    quarantined_names: tuple[str, ...]
    private_manifest_bytes: bytes | None

    @property
    def total_uncompressed_bytes(self) -> int:
        return sum(entry.uncompressed_bytes for entry in self.entries)


def _fail(
    reason: CorpusIntegrityReason, *, entry_index: int | None = None
) -> CorpusIntegrityError:
    return CorpusIntegrityError(reason, entry_index=entry_index)


def _parse_extra_fields(extra: bytes) -> tuple[tuple[int, bytes], ...]:
    fields: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 4 <= len(extra):
        header_id = int.from_bytes(extra[offset : offset + 2], "little")
        data_size = int.from_bytes(extra[offset + 2 : offset + 4], "little")
        start = offset + 4
        end = start + data_size
        if end > len(extra):
            break
        fields.append((header_id, extra[start:end]))
        offset = end
    return tuple(fields)


def _declares_link_payload(info: zipfile.ZipInfo) -> bool:
    """Detect an Info-ZIP Unix1 link payload on an entry claiming regular mode.

    A hard or symbolic link stored with forged permission bits still carries the
    variable link payload in extra field 0x000d.  Trusting the mode bits alone
    would let that entry pass as a regular file.
    """

    for header_id, payload in _parse_extra_fields(info.extra):
        if header_id == _INFOZIP_UNIX1_EXTRA_ID and len(payload) > _INFOZIP_UNIX1_FIXED_BYTES:
            return True
    return False


def _assert_entry_name_is_safe(index: int, name: str) -> None:
    if len(name) > MAX_ENTRY_NAME_LENGTH:
        raise _fail(CorpusIntegrityReason.entry_name_length_exceeded, entry_index=index)
    if not name:
        raise _fail(CorpusIntegrityReason.entry_name_not_portable, entry_index=index)
    if name != unicodedata.normalize("NFC", name):
        raise _fail(CorpusIntegrityReason.entry_name_not_portable, entry_index=index)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
        raise _fail(CorpusIntegrityReason.entry_name_not_portable, entry_index=index)
    if "\\" in name:
        raise _fail(CorpusIntegrityReason.drive_or_unc_entry_path, entry_index=index)
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        raise _fail(CorpusIntegrityReason.drive_or_unc_entry_path, entry_index=index)
    if name.startswith("/"):
        raise _fail(CorpusIntegrityReason.absolute_entry_path, entry_index=index)
    if name.endswith("/"):
        raise _fail(CorpusIntegrityReason.directory_entry, entry_index=index)
    components = name.split("/")
    if any(component == ".." for component in components):
        raise _fail(CorpusIntegrityReason.parent_traversal_entry_path, entry_index=index)
    if any(component in ("", ".") for component in components):
        raise _fail(CorpusIntegrityReason.entry_name_not_portable, entry_index=index)
    # At most one bundle directory is tolerated.  Deeper nesting adds traversal
    # surface without adding evaluator value.
    if len(components) > 2:
        raise _fail(CorpusIntegrityReason.unexpected_entry_name, entry_index=index)


def _resolve_archive_root(names: tuple[str, ...]) -> str:
    """Return the single bundle directory prefix, or an empty string if flat.

    A mixed layout — some members at the top level and some under a directory,
    or more than one directory — is rejected: it would make the effective
    member name ambiguous.
    """

    roots = {name.split("/")[0] if "/" in name else "" for name in names}
    if len(roots) != 1:
        raise _fail(CorpusIntegrityReason.unexpected_entry_name)
    root = roots.pop()
    return f"{root}/" if root else ""


def _assert_entry_type_is_regular(index: int, info: zipfile.ZipInfo) -> None:
    if info.is_dir():
        raise _fail(CorpusIntegrityReason.directory_entry, entry_index=index)
    mode = info.external_attr >> 16
    if info.create_system == _UNIX_CREATE_SYSTEM and mode:
        if stat.S_ISLNK(mode):
            raise _fail(CorpusIntegrityReason.symlink_entry, entry_index=index)
        if stat.S_ISDIR(mode):
            raise _fail(CorpusIntegrityReason.directory_entry, entry_index=index)
        if (
            stat.S_ISCHR(mode)
            or stat.S_ISBLK(mode)
            or stat.S_ISFIFO(mode)
            or stat.S_ISSOCK(mode)
        ):
            raise _fail(CorpusIntegrityReason.device_entry, entry_index=index)
        if not stat.S_ISREG(mode):
            raise _fail(CorpusIntegrityReason.device_entry, entry_index=index)
    if _declares_link_payload(info):
        raise _fail(CorpusIntegrityReason.hardlink_entry, entry_index=index)


def _assert_not_nested_archive(index: int, data: bytes) -> None:
    if any(data.startswith(prefix) for prefix in _NESTED_ARCHIVE_PREFIXES):
        raise _fail(CorpusIntegrityReason.nested_archive_entry, entry_index=index)
    window = data[_TAR_MAGIC_OFFSET : _TAR_MAGIC_OFFSET + 8]
    if any(window.startswith(magic) for magic in _TAR_MAGICS):
        raise _fail(CorpusIntegrityReason.nested_archive_entry, entry_index=index)


def _read_member_bytes(
    archive: zipfile.ZipFile, index: int, info: zipfile.ZipInfo, limit: int
) -> bytes:
    try:
        with archive.open(info) as handle:
            # Read one byte past the limit so an entry that lies about its
            # declared size is still bounded and still rejected.
            data = handle.read(limit + 1)
    except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
        raise _fail(
            CorpusIntegrityReason.entry_checksum_mismatch, entry_index=index
        ) from exc
    if len(data) > limit:
        raise _fail(CorpusIntegrityReason.entry_size_limit_exceeded, entry_index=index)
    if len(data) != info.file_size:
        raise _fail(CorpusIntegrityReason.declared_size_mismatch, entry_index=index)
    return data


def read_public_corpus_archive(
    archive_path: Path,
    *,
    expected_sha256: str = PUBLIC_CORPUS_ZIP_SHA256,
) -> SafeArchiveInventory:
    """Validate and safely read the authorised public corpus archive.

    Every structural, size, path, link, duplication, allowlist, and encoding
    rule is enforced before any member content is handed to a parser, and no
    member is ever written to the filesystem.
    """

    contract = stage7_evaluation_contract()
    max_member_bytes = contract.corpus.max_archive_member_bytes
    max_total_bytes = contract.corpus.max_archive_total_bytes

    if not archive_path.exists():
        raise _fail(CorpusIntegrityReason.archive_missing)
    if not archive_path.is_file() or archive_path.is_symlink():
        raise _fail(CorpusIntegrityReason.archive_not_regular_file)
    archive_size = archive_path.stat().st_size
    if archive_size > MAX_ARCHIVE_FILE_BYTES:
        raise _fail(CorpusIntegrityReason.archive_byte_limit_exceeded)

    raw = archive_path.read_bytes()
    if not raw.startswith(_ZIP_LOCAL_HEADER_MAGIC):
        raise _fail(CorpusIntegrityReason.archive_magic_mismatch)
    archive_sha256 = hashlib.sha256(raw).hexdigest()
    if archive_sha256 != expected_sha256:
        raise _fail(CorpusIntegrityReason.archive_sha256_mismatch)

    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise _fail(CorpusIntegrityReason.archive_not_readable_zip) from exc

    allowed_readable = frozenset(
        REQUIRED_ARCHIVE_MEMBERS + OPTIONAL_READABLE_ARCHIVE_MEMBERS
    )
    quarantined = frozenset(QUARANTINED_ARCHIVE_MEMBERS)
    forbidden = frozenset(FORBIDDEN_ARCHIVE_MEMBERS)

    entries: list[ArchiveEntryEvidence] = []
    members: dict[str, bytes] = {}
    quarantined_names: list[str] = []
    private_manifest_bytes: bytes | None = None
    seen_names: set[str] = set()
    seen_folded: set[str] = set()
    total_uncompressed = 0

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRY_COUNT:
            raise _fail(CorpusIntegrityReason.entry_count_limit_exceeded)

        for index, info in enumerate(infos):
            _assert_entry_name_is_safe(index, info.filename)
        root_prefix = _resolve_archive_root(tuple(info.filename for info in infos))

        for index, info in enumerate(infos):
            # Names are validated raw before the bundle prefix is removed, so
            # stripping can never turn an unsafe path into a safe-looking one.
            name = info.filename[len(root_prefix) :]
            if not name:
                raise _fail(CorpusIntegrityReason.directory_entry, entry_index=index)
            _assert_entry_type_is_regular(index, info)

            if name in seen_names:
                raise _fail(
                    CorpusIntegrityReason.duplicate_entry_name, entry_index=index
                )
            folded = unicodedata.normalize("NFC", name).casefold()
            if folded in seen_folded:
                raise _fail(
                    CorpusIntegrityReason.case_insensitive_duplicate_entry_name,
                    entry_index=index,
                )
            seen_names.add(name)
            seen_folded.add(folded)

            if name in forbidden:
                raise _fail(
                    CorpusIntegrityReason.forbidden_private_entry_name, entry_index=index
                )
            if name not in allowed_readable and name not in quarantined:
                raise _fail(
                    CorpusIntegrityReason.unexpected_entry_name, entry_index=index
                )

            if info.flag_bits & 0x1:
                raise _fail(CorpusIntegrityReason.encrypted_entry, entry_index=index)
            if info.compress_type not in _ALLOWED_COMPRESSION_METHODS:
                raise _fail(
                    CorpusIntegrityReason.unsupported_compression_method,
                    entry_index=index,
                )
            if info.file_size > max_member_bytes:
                raise _fail(
                    CorpusIntegrityReason.entry_size_limit_exceeded, entry_index=index
                )
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise _fail(
                        CorpusIntegrityReason.compression_ratio_limit_exceeded,
                        entry_index=index,
                    )

            total_uncompressed += info.file_size
            if total_uncompressed > max_total_bytes:
                raise _fail(CorpusIntegrityReason.total_uncompressed_limit_exceeded)

            data = _read_member_bytes(archive, index, info, max_member_bytes)
            _assert_not_nested_archive(index, data)

            entries.append(
                ArchiveEntryEvidence(
                    index=index,
                    name=name,
                    compressed_bytes=info.compress_size,
                    uncompressed_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )

            if name in quarantined:
                quarantined_names.append(name)
                if name == PRIVATE_MANIFEST_MEMBER:
                    private_manifest_bytes = data
                continue

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _fail(
                    CorpusIntegrityReason.entry_not_utf8, entry_index=index
                ) from exc
            if text.startswith("﻿") or "\x00" in text:
                raise _fail(CorpusIntegrityReason.entry_not_utf8, entry_index=index)
            members[name] = data

    for required in REQUIRED_ARCHIVE_MEMBERS:
        if required not in members:
            raise _fail(CorpusIntegrityReason.missing_required_entry)

    return SafeArchiveInventory(
        policy_version=ARCHIVE_POLICY_VERSION,
        archive_sha256=archive_sha256,
        archive_bytes=archive_size,
        entries=tuple(entries),
        members=dict(members),
        quarantined_names=tuple(quarantined_names),
        private_manifest_bytes=private_manifest_bytes,
    )
