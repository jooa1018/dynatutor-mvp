"""Stage 7 Lane A: corpus archive integrity and safe extraction.

Every fixture archive here is built in-process from independently authored
Korean sentences.  No public or private corpus material is read, imported, or
committed by this suite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import struct
import zipfile

import pytest

from evaluation.phase56_stage7.contracts import (
    Stage7ExpectedTerminal,
    Stage7FailureKind,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.corpus_integrity import (
    MAX_ARCHIVE_ENTRY_COUNT,
    MAX_ARCHIVE_FILE_BYTES,
    CorpusIntegrityError,
    CorpusIntegrityReason,
    read_public_corpus_archive,
)
from evaluation.phase56_stage7.corpus_preflight import (
    assert_corpus_modules_are_execution_free,
    assert_raw_corpus_is_not_committed,
    run_corpus_integrity_preflight,
)
from evaluation.phase56_stage7.corpus_records import (
    CorpusRecordError,
    CorpusRecordReason,
    parse_public_jsonl,
    parse_schema_document,
)
from evaluation.phase56_stage7.corpus_semantics import (
    CorpusSemanticError,
    CorpusSemanticReason,
    assert_private_manifest_is_keys_only,
    scope_adjusted_expected_terminal,
    verify_corpus_semantics,
    verify_manifest,
    verify_validation_report,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.network_guard import block_external_network
from evaluation.phase56_stage7.preflight import PreflightTerminal


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SCHEMA_FIELDS = (
    "case_id",
    "split",
    "family",
    "problem_text",
    "problem_sha256",
    "evidence_quotes",
    "facts",
    "reference_answer",
    "expected_terminal",
    "chapter",
)
SCHEMA_DOCUMENT = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {name: {"type": "string"} for name in SCHEMA_FIELDS},
}

SUPPORTED_FAMILIES = (
    "constant_acceleration_1d",
    "newton_second_law",
    "work_energy",
    "impulse_momentum",
    "fixed_axis_rotation",
)
DEFERRED_FAMILIES = (
    "spring_mass_vibration",
    "relative_acceleration_translation",
    "coriolis_relative_motion",
    "slot_pin_relative_motion",
)


# --------------------------------------------------------------------------
# Independently authored synthetic corpus construction
# --------------------------------------------------------------------------


def _case(
    *,
    index: int,
    split: PublicSplit,
    family: str,
    terminal: str,
    with_answer: bool,
) -> dict[str, object]:
    mass = round(1.0 + index * 0.25, 4)
    accel = round(2.0 + index * 0.5, 4)
    problem_text = (
        f"연습 문제 {split.value} {index}: 수평면 위의 물체에서 "
        f"질량은 {mass} kg 이고 가속도는 {accel} m/s^2 이다. 알짜힘을 구하시오."
    )
    quotes = [f"질량은 {mass} kg", f"가속도는 {accel} m/s^2"]
    record: dict[str, object] = {
        "case_id": f"{split.value}-{index:04d}",
        "split": split.value,
        "family": family,
        "problem_text": problem_text,
        "problem_sha256": hashlib.sha256(problem_text.encode("utf-8")).hexdigest(),
        "evidence_quotes": quotes,
        "facts": [
            {"semantic_role": "mass", "value": mass, "unit": "kg"},
            {"semantic_role": "acceleration", "value": accel, "unit": "m/s^2"},
        ],
        "expected_terminal": terminal,
        "chapter": "ch12",
    }
    if with_answer:
        record["reference_answer"] = {"value": round(mass * accel, 6), "unit": "N"}
    return record


def build_public_dev_records() -> list[dict[str, object]]:
    """84 development cases: 72 in-scope supported plus 12 deferred families."""

    records: list[dict[str, object]] = []
    for index in range(72):
        records.append(
            _case(
                index=index,
                split=PublicSplit.public_dev,
                family=SUPPORTED_FAMILIES[index % len(SUPPORTED_FAMILIES)],
                terminal="accepted",
                with_answer=True,
            )
        )
    for offset in range(12):
        records.append(
            _case(
                index=100 + offset,
                split=PublicSplit.public_dev,
                # The corpus still declares "accepted"; current course scope is
                # what withdraws answer authority for these four families.
                family=DEFERRED_FAMILIES[offset % len(DEFERRED_FAMILIES)],
                terminal="accepted",
                with_answer=True,
            )
        )
    return records


def build_public_adversarial_records() -> list[dict[str, object]]:
    """16 adversarial cases: 9 supported, 2/2/2/1 blocked classes."""

    plan: list[tuple[str, bool]] = (
        [("accepted", True)] * 9
        + [("needs_figure", False)] * 2
        + [("needs_confirmation", False)] * 2
        + [("unsupported", False)] * 2
        + [("insufficient_information", False)]
    )
    return [
        _case(
            index=index,
            split=PublicSplit.public_adversarial,
            family=SUPPORTED_FAMILIES[index % len(SUPPORTED_FAMILIES)],
            terminal=terminal,
            with_answer=with_answer,
        )
        for index, (terminal, with_answer) in enumerate(plan)
    ]


def _jsonl(records: list[dict[str, object]]) -> bytes:
    return (
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"
    ).encode("utf-8")


def default_members() -> dict[str, bytes]:
    return {
        "public_dev.jsonl": _jsonl(build_public_dev_records()),
        "public_adversarial.jsonl": _jsonl(build_public_adversarial_records()),
        "schema.json": json.dumps(SCHEMA_DOCUMENT, ensure_ascii=False).encode("utf-8"),
    }


def write_archive(
    path: Path,
    members: dict[str, bytes],
    *,
    external_attr: dict[str, int] | None = None,
    extra: dict[str, bytes] | None = None,
    compress_type: dict[str, int] | None = None,
    flag_bits: dict[str, int] | None = None,
    declared_size: dict[str, int] | None = None,
    duplicate: tuple[str, bytes] | None = None,
) -> Path:
    external_attr = external_attr or {}
    extra = extra or {}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        items = list(members.items())
        if duplicate is not None:
            items.append(duplicate)
        for name, payload in items:
            info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = external_attr.get(name, 0o100644 << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            if name in extra:
                info.extra = extra[name]
            archive.writestr(info, payload)
    # ``writestr`` normalises the general-purpose flag and recomputes sizes, so
    # hostile header values are forged directly in the central directory.
    for name, bits in (flag_bits or {}).items():
        _patch_central_directory(path, name, field_offset=8, value=bits, width=2)
    for name, method in (compress_type or {}).items():
        _patch_central_directory(path, name, field_offset=10, value=method, width=2)
    for name, size in (declared_size or {}).items():
        _patch_central_directory(path, name, field_offset=24, value=size, width=4)
    return path


def _patch_central_directory(
    path: Path, name: str, *, field_offset: int, value: int, width: int
) -> None:
    raw = bytearray(path.read_bytes())
    encoded = name.encode("utf-8")
    offset = 0
    while True:
        offset = raw.find(b"PK\x01\x02", offset)
        if offset < 0:
            raise AssertionError(f"central directory record not found: {name}")
        name_length = struct.unpack_from("<H", raw, offset + 28)[0]
        start = offset + 46
        if raw[start : start + name_length] == encoded:
            fmt = "<H" if width == 2 else "<I"
            struct.pack_into(fmt, raw, offset + field_offset, value)
            break
        offset += 4
    path.write_bytes(bytes(raw))


def archive_with(tmp_path: Path, **kwargs) -> tuple[Path, str]:
    members = kwargs.pop("members", None) or default_members()
    path = write_archive(tmp_path / "corpus.zip", members, **kwargs)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def expect_reason(
    tmp_path: Path, reason: CorpusIntegrityReason, **kwargs
) -> CorpusIntegrityError:
    path, digest = archive_with(tmp_path, **kwargs)
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason is reason
    return excinfo.value


# --------------------------------------------------------------------------
# Archive-level integrity
# --------------------------------------------------------------------------


def test_authorised_archive_is_read_safely_in_memory(tmp_path: Path) -> None:
    path, digest = archive_with(tmp_path)
    inventory = read_public_corpus_archive(path, expected_sha256=digest)
    assert inventory.archive_sha256 == digest
    assert set(inventory.members) == {
        "public_dev.jsonl",
        "public_adversarial.jsonl",
        "schema.json",
    }
    assert inventory.quarantined_names == ()
    assert inventory.private_manifest_bytes is None
    assert len(inventory.entries) == 3
    assert inventory.total_uncompressed_bytes > 0
    # Reading the archive materialises nothing beyond the archive itself.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["corpus.zip"]


def test_frozen_expected_zip_sha256_is_the_default_authorisation(tmp_path: Path) -> None:
    path, digest = archive_with(tmp_path)
    contract = stage7_evaluation_contract()
    assert digest != contract.corpus.expected_zip_sha256
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path)
    assert excinfo.value.reason is CorpusIntegrityReason.archive_sha256_mismatch


def test_archive_sha256_mismatch_is_rejected(tmp_path: Path) -> None:
    path, _ = archive_with(tmp_path)
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256="0" * 64)
    assert excinfo.value.reason is CorpusIntegrityReason.archive_sha256_mismatch


def test_archive_magic_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "corpus.zip"
    path.write_bytes(b"NOTAZIP" + b"\x00" * 64)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason is CorpusIntegrityReason.archive_magic_mismatch


def test_missing_archive_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(tmp_path / "absent.zip", expected_sha256="0" * 64)
    assert excinfo.value.reason is CorpusIntegrityReason.archive_missing


def test_archive_byte_limit_is_enforced(tmp_path: Path, monkeypatch) -> None:
    path, digest = archive_with(tmp_path)
    monkeypatch.setattr(
        "evaluation.phase56_stage7.corpus_integrity.MAX_ARCHIVE_FILE_BYTES", 16
    )
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason is CorpusIntegrityReason.archive_byte_limit_exceeded
    assert MAX_ARCHIVE_FILE_BYTES == 10_000_000


def test_entry_count_limit_is_enforced(tmp_path: Path) -> None:
    members = default_members()
    for index in range(MAX_ARCHIVE_ENTRY_COUNT + 1):
        members[f"README.md{index}"] = b"x"
    expect_reason(
        tmp_path, CorpusIntegrityReason.entry_count_limit_exceeded, members=members
    )


def test_per_entry_size_limit_is_enforced(tmp_path: Path, monkeypatch) -> None:
    path, digest = archive_with(tmp_path)
    contract = stage7_evaluation_contract()
    assert contract.corpus.max_archive_member_bytes == 2_000_000

    class _Shrunk:
        max_archive_member_bytes = 32
        max_archive_total_bytes = contract.corpus.max_archive_total_bytes

    monkeypatch.setattr(
        "evaluation.phase56_stage7.corpus_integrity.stage7_evaluation_contract",
        lambda: type("C", (), {"corpus": _Shrunk})(),
    )
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason is CorpusIntegrityReason.entry_size_limit_exceeded


def test_total_uncompressed_limit_is_enforced(tmp_path: Path, monkeypatch) -> None:
    path, digest = archive_with(tmp_path)
    contract = stage7_evaluation_contract()

    class _Shrunk:
        max_archive_member_bytes = contract.corpus.max_archive_member_bytes
        max_archive_total_bytes = 64

    monkeypatch.setattr(
        "evaluation.phase56_stage7.corpus_integrity.stage7_evaluation_contract",
        lambda: type("C", (), {"corpus": _Shrunk})(),
    )
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason is (
        CorpusIntegrityReason.total_uncompressed_limit_exceeded
    )


def test_compression_ratio_limit_rejects_a_zip_bomb(tmp_path: Path) -> None:
    members = default_members()
    members["README.md"] = b"\x00" * 1_000_000
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.compression_ratio_limit_exceeded,
        members=members,
    )


@pytest.mark.parametrize(
    ("name", "reason"),
    (
        ("../public_dev.jsonl", CorpusIntegrityReason.parent_traversal_entry_path),
        ("a/../../public_dev.jsonl", CorpusIntegrityReason.parent_traversal_entry_path),
        ("/etc/passwd", CorpusIntegrityReason.absolute_entry_path),
        ("C:\\windows\\system32", CorpusIntegrityReason.drive_or_unc_entry_path),
        ("\\\\server\\share", CorpusIntegrityReason.drive_or_unc_entry_path),
        ("nested/public_dev.jsonl", CorpusIntegrityReason.unexpected_entry_name),
        ("evil\nname.jsonl", CorpusIntegrityReason.entry_name_not_portable),
        ("x" * 200, CorpusIntegrityReason.entry_name_length_exceeded),
    ),
)
def test_unsafe_entry_paths_are_rejected(
    tmp_path: Path, name: str, reason: CorpusIntegrityReason
) -> None:
    members = default_members()
    members[name] = b"payload"
    expect_reason(tmp_path, reason, members=members)


def test_directory_entry_is_rejected(tmp_path: Path) -> None:
    members = default_members()
    members["fixtures/"] = b""
    expect_reason(tmp_path, CorpusIntegrityReason.directory_entry, members=members)


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    members = default_members()
    members["README.md"] = b"/etc/passwd"
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.symlink_entry,
        members=members,
        external_attr={"README.md": (0o120777 << 16)},
    )


def test_device_entry_is_rejected(tmp_path: Path) -> None:
    members = default_members()
    members["README.md"] = b""
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.device_entry,
        members=members,
        external_attr={"README.md": (0o020666 << 16)},
    )


def test_link_payload_on_a_forged_regular_entry_is_rejected(tmp_path: Path) -> None:
    """Mode bits alone are not trusted: a link payload still rejects the entry."""

    members = default_members()
    members["README.md"] = b"target"
    link_payload = b"\x00" * 12 + b"/etc/passwd"
    unix1_extra = struct.pack("<HH", 0x000D, len(link_payload)) + link_payload
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.hardlink_entry,
        members=members,
        external_attr={"README.md": (0o100644 << 16)},
        extra={"README.md": unix1_extra},
    )


def test_duplicate_and_case_insensitive_duplicate_entries_are_rejected(
    tmp_path: Path,
) -> None:
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.duplicate_entry_name,
        duplicate=("schema.json", b"{}"),
    )
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.case_insensitive_duplicate_entry_name,
        duplicate=("Schema.JSON", b"{}"),
    )


def test_unexpected_and_forbidden_member_names_are_rejected(tmp_path: Path) -> None:
    members = default_members()
    members["surprise.bin"] = b"x"
    expect_reason(tmp_path, CorpusIntegrityReason.unexpected_entry_name, members=members)

    members = default_members()
    members["DO_NOT_SHARE_WITH_CODEX_private_heldout.jsonl"] = b"x"
    expect_reason(
        tmp_path, CorpusIntegrityReason.forbidden_private_entry_name, members=members
    )

    members = default_members()
    members["all_cases.jsonl"] = b"x"
    expect_reason(
        tmp_path, CorpusIntegrityReason.forbidden_private_entry_name, members=members
    )


def test_missing_required_member_is_rejected(tmp_path: Path) -> None:
    members = default_members()
    del members["schema.json"]
    expect_reason(
        tmp_path, CorpusIntegrityReason.missing_required_entry, members=members
    )


def test_encrypted_and_unsupported_compression_entries_are_rejected(
    tmp_path: Path,
) -> None:
    members = default_members()
    members["README.md"] = b"x"
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.encrypted_entry,
        members=members,
        flag_bits={"README.md": 0x1},
    )
    expect_reason(
        tmp_path,
        CorpusIntegrityReason.unsupported_compression_method,
        members=members,
        compress_type={"README.md": zipfile.ZIP_BZIP2},
    )


def test_forged_declared_size_is_rejected(tmp_path: Path) -> None:
    """A forged uncompressed size never yields silently truncated content.

    CRC verification usually fires first; the explicit size cross-check remains
    as defence in depth for either ordering.
    """

    members = default_members()
    members["README.md"] = b"honest payload"
    path, digest = archive_with(
        tmp_path, members=members, declared_size={"README.md": 3}
    )
    with pytest.raises(CorpusIntegrityError) as excinfo:
        read_public_corpus_archive(path, expected_sha256=digest)
    assert excinfo.value.reason in (
        CorpusIntegrityReason.declared_size_mismatch,
        CorpusIntegrityReason.entry_checksum_mismatch,
    )


@pytest.mark.parametrize(
    "payload",
    (
        b"PK\x03\x04nested",
        b"\x1f\x8bgzip",
        b"BZhbzip2",
        b"\xfd7zXZ\x00xz",
        b"7z\xbc\xaf\x27\x1cseven",
        b"Rar!\x1a\x07rar",
        b"\x00" * 257 + b"ustar\x0000" + b"\x00" * 16,
    ),
)
def test_nested_archive_members_are_rejected(tmp_path: Path, payload: bytes) -> None:
    members = default_members()
    members["README.md"] = payload
    expect_reason(tmp_path, CorpusIntegrityReason.nested_archive_entry, members=members)


def test_non_utf8_member_is_rejected(tmp_path: Path) -> None:
    members = default_members()
    members["README.md"] = b"\xff\xfe\x00invalid"
    expect_reason(tmp_path, CorpusIntegrityReason.entry_not_utf8, members=members)


def test_quarantined_members_are_present_allowed_but_never_parsed(
    tmp_path: Path,
) -> None:
    members = default_members()
    members["public_all.jsonl"] = b"{}"
    members["private_heldout_manifest_without_text.json"] = json.dumps(
        {"case_count": 40, "families": ["a", "b"]}
    ).encode("utf-8")
    path, digest = archive_with(tmp_path, members=members)
    inventory = read_public_corpus_archive(path, expected_sha256=digest)
    assert "public_all.jsonl" not in inventory.members
    assert "private_heldout_manifest_without_text.json" not in inventory.members
    assert set(inventory.quarantined_names) == {
        "public_all.jsonl",
        "private_heldout_manifest_without_text.json",
    }
    assert inventory.private_manifest_bytes is not None


# --------------------------------------------------------------------------
# Schema binding and record parsing
# --------------------------------------------------------------------------


def _declared() -> frozenset[str]:
    return parse_schema_document(
        json.dumps(SCHEMA_DOCUMENT, ensure_ascii=False).encode("utf-8")
    )


def _parse_dev(records: list[dict[str, object]]):
    return parse_public_jsonl(
        _jsonl(records), split=PublicSplit.public_dev, declared_schema_fields=_declared()
    )


def test_schema_document_shapes_are_accepted_or_fail_closed() -> None:
    assert "case_id" in _declared()
    assert parse_schema_document(
        json.dumps({"fields": ["case_id", "split"]}).encode("utf-8")
    ) == frozenset({"case_id", "split"})
    assert parse_schema_document(
        json.dumps({"fields": [{"name": "case_id"}]}).encode("utf-8")
    ) == frozenset({"case_id"})
    with pytest.raises(CorpusRecordError) as excinfo:
        parse_schema_document(json.dumps({"unknown": True}).encode("utf-8"))
    assert excinfo.value.reason is CorpusRecordReason.schema_declaration_unrecognized


def test_records_parse_into_normalised_gold_domain_cases() -> None:
    cases = _parse_dev(build_public_dev_records())
    assert len(cases) == 84
    assert cases[0].split is PublicSplit.public_dev
    assert cases[0].reference_answer is not None
    assert len(cases[0].facts) == 2


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (lambda r: r.update({"case_id": None}), CorpusRecordReason.invalid_field_type),
        (lambda r: r.pop("case_id"), CorpusRecordReason.missing_required_field),
        (lambda r: r.pop("facts"), CorpusRecordReason.missing_required_field),
        (lambda r: r.update({"id": "dup"}), CorpusRecordReason.ambiguous_field_binding),
        (
            lambda r: r.update({"private_note": "x"}),
            CorpusRecordReason.private_marker_in_public_record,
        ),
        (
            lambda r: r.update({"heldOut": "x"}),
            CorpusRecordReason.private_marker_in_public_record,
        ),
        (
            lambda r: r.update({"reference_answer": {"value": float("nan")}}),
            CorpusRecordReason.invalid_field_type,
        ),
        (
            lambda r: r.update(
                {"facts": [{"semantic_role": "mass", "value": float("inf")}]}
            ),
            CorpusRecordReason.invalid_field_type,
        ),
        (lambda r: r.update({"split": "private_dev"}), CorpusRecordReason.unknown_split_label),
        (
            lambda r: r.update({"split": "public_adversarial"}),
            CorpusRecordReason.unknown_split_label,
        ),
    ),
)
def test_record_defects_fail_closed(mutate, reason: CorpusRecordReason) -> None:
    records = build_public_dev_records()
    mutate(records[0])
    with pytest.raises(CorpusRecordError) as excinfo:
        _parse_dev(records)
    assert excinfo.value.reason is reason


def test_undeclared_bound_field_is_rejected() -> None:
    reduced = frozenset(SCHEMA_FIELDS) - {"problem_sha256"}
    with pytest.raises(CorpusRecordError) as excinfo:
        parse_public_jsonl(
            _jsonl(build_public_dev_records()),
            split=PublicSplit.public_dev,
            declared_schema_fields=reduced,
        )
    assert excinfo.value.reason is CorpusRecordReason.undeclared_bound_field


def test_inconsistent_alias_binding_across_records_is_rejected() -> None:
    records = build_public_dev_records()
    second = records[1]
    second["id"] = second.pop("case_id")
    declared = frozenset(SCHEMA_FIELDS) | {"id"}
    with pytest.raises(CorpusRecordError) as excinfo:
        parse_public_jsonl(
            _jsonl(records),
            split=PublicSplit.public_dev,
            declared_schema_fields=declared,
        )
    assert excinfo.value.reason is CorpusRecordReason.inconsistent_field_binding


def test_optional_field_absence_is_not_binding_drift() -> None:
    records = build_public_dev_records()
    records[0].pop("chapter")
    assert len(_parse_dev(records)) == 84


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (b'\n{"a": 1}\n', CorpusRecordReason.blank_jsonl_line),
        (b'   \n{"a": 1}\n', CorpusRecordReason.blank_jsonl_line),
        (b"{not json}\n", CorpusRecordReason.invalid_json),
        (b"[1,2,3]\n", CorpusRecordReason.record_not_object),
    ),
)
def test_jsonl_framing_defects_fail_closed(
    payload: bytes, reason: CorpusRecordReason
) -> None:
    with pytest.raises(CorpusRecordError) as excinfo:
        parse_public_jsonl(
            payload, split=PublicSplit.public_dev, declared_schema_fields=_declared()
        )
    assert excinfo.value.reason is reason


# --------------------------------------------------------------------------
# Semantic integrity and scope-adjusted distribution
# --------------------------------------------------------------------------


def _parsed_corpus():
    dev = _parse_dev(build_public_dev_records())
    adversarial = parse_public_jsonl(
        _jsonl(build_public_adversarial_records()),
        split=PublicSplit.public_adversarial,
        declared_schema_fields=_declared(),
    )
    return dev, adversarial


def test_scope_adjusted_distribution_matches_the_frozen_contract() -> None:
    dev, adversarial = _parsed_corpus()
    evidence = verify_corpus_semantics(public_dev=dev, public_adversarial=adversarial)
    contract = stage7_evaluation_contract()
    assert evidence.public_dev_count == 84
    assert evidence.public_adversarial_count == 16
    assert evidence.distribution.supported_accepted == 81
    assert evidence.distribution.deferred_unsupported == 12
    assert evidence.distribution.unsupported_other == 2
    assert evidence.distribution.needs_figure == 2
    assert evidence.distribution.needs_confirmation == 2
    assert evidence.distribution.insufficient_information == 1
    assert evidence.distribution.total == contract.expected_terminals.total
    assert {family for family, _ in evidence.deferred_family_counts} == set(
        contract.course_scope.deferred_families
    )


def test_current_scope_overrides_a_corpus_declared_accepted_terminal() -> None:
    dev = _parse_dev(build_public_dev_records())
    deferred = [case for case in dev if case.family in DEFERRED_FAMILIES]
    assert len(deferred) == 12
    for case in deferred:
        assert case.declared_terminal == "accepted"
        assert (
            scope_adjusted_expected_terminal(case, case_index=0)
            is Stage7ExpectedTerminal.deferred_unsupported
        )


def test_scope_mapping_uses_no_case_id_or_split_authority() -> None:
    dev = _parse_dev(build_public_dev_records())
    supported = next(case for case in dev if case.family in SUPPORTED_FAMILIES)
    renamed = supported.model_copy(
        update={"case_id": "totally-different-id", "chapter": "ch99"}
    )
    assert scope_adjusted_expected_terminal(
        renamed, case_index=0
    ) is scope_adjusted_expected_terminal(supported, case_index=0)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (
            lambda dev, adv: (dev[:-1], adv),
            CorpusSemanticReason.split_count_mismatch,
        ),
        (
            lambda dev, adv: (
                dev[:-1] + (dev[0].model_copy(update={"case_id": "dup-id"}),) * 1,
                adv,
            ),
            CorpusSemanticReason.duplicate_problem_text,
        ),
    ),
)
def test_split_and_duplication_defects_fail_closed(mutate, reason) -> None:
    dev, adversarial = _parsed_corpus()
    mutated_dev, mutated_adv = mutate(dev, adversarial)
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(
            public_dev=mutated_dev, public_adversarial=mutated_adv
        )
    assert excinfo.value.reason is reason


def test_duplicate_case_id_across_splits_is_rejected() -> None:
    dev, adversarial = _parsed_corpus()
    collided = adversarial[0].model_copy(update={"case_id": dev[0].case_id})
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(
            public_dev=dev, public_adversarial=(collided,) + adversarial[1:]
        )
    assert excinfo.value.reason is CorpusSemanticReason.splits_not_disjoint


@pytest.mark.parametrize(
    ("update", "reason"),
    (
        ({"problem_sha256": "9" * 64}, CorpusSemanticReason.problem_hash_mismatch),
        (
            {
                "problem_text": "A block of mass 2 kg accelerates.",
                "problem_sha256": hashlib.sha256(
                    "A block of mass 2 kg accelerates.".encode("utf-8")
                ).hexdigest(),
            },
            CorpusSemanticReason.problem_text_not_korean,
        ),
        (
            {"evidence_quotes": ("문제에 없는 인용문입니다",)},
            CorpusSemanticReason.evidence_quote_absent_from_problem,
        ),
        ({"reference_answer": None}, CorpusSemanticReason.missing_reference_answer_for_accepted),
        ({"declared_terminal": "완전히_모르는_라벨"}, CorpusSemanticReason.unknown_terminal_label),
    ),
)
def test_case_semantic_defects_fail_closed(update, reason) -> None:
    dev, adversarial = _parsed_corpus()
    mutated = (dev[0].model_copy(update=update),) + dev[1:]
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(public_dev=mutated, public_adversarial=adversarial)
    assert excinfo.value.reason is reason


def test_fact_value_absent_from_evidence_is_rejected() -> None:
    from evaluation.phase56_stage7.corpus_records import CorpusFactV1

    dev, adversarial = _parsed_corpus()
    invented = dev[0].model_copy(
        update={"facts": dev[0].facts + (CorpusFactV1(role="mass", value=987.654),)}
    )
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(
            public_dev=(invented,) + dev[1:], public_adversarial=adversarial
        )
    assert excinfo.value.reason is CorpusSemanticReason.fact_value_absent_from_evidence


def test_blocked_case_carrying_a_reference_answer_is_rejected() -> None:
    from evaluation.phase56_stage7.corpus_records import CorpusReferenceAnswerV1

    dev, adversarial = _parsed_corpus()
    blocked_index = next(
        index
        for index, case in enumerate(adversarial)
        if case.declared_terminal == "needs_figure"
    )
    leaked = adversarial[blocked_index].model_copy(
        update={"reference_answer": CorpusReferenceAnswerV1(value=1.0, unit="N")}
    )
    mutated = adversarial[:blocked_index] + (leaked,) + adversarial[blocked_index + 1 :]
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(public_dev=dev, public_adversarial=mutated)
    assert excinfo.value.reason is (
        CorpusSemanticReason.unexpected_reference_answer_for_blocked
    )


def test_scope_terminal_count_mismatch_fails_closed() -> None:
    dev, adversarial = _parsed_corpus()
    # Move one deferred case into an in-scope family: 82/11 no longer matches.
    deferred_index = next(
        index for index, case in enumerate(dev) if case.family in DEFERRED_FAMILIES
    )
    retargeted = dev[deferred_index].model_copy(
        update={"family": SUPPORTED_FAMILIES[0]}
    )
    mutated = dev[:deferred_index] + (retargeted,) + dev[deferred_index + 1 :]
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_corpus_semantics(public_dev=mutated, public_adversarial=adversarial)
    assert excinfo.value.reason is CorpusSemanticReason.scope_terminal_count_mismatch


# --------------------------------------------------------------------------
# Manifest, validation report, private manifest
# --------------------------------------------------------------------------


def test_manifest_is_cross_checked_against_observed_evidence() -> None:
    digest = "a" * 64
    verify_manifest(
        json.dumps(
            {"files": {"public_dev.jsonl": digest}, "counts": {"public_dev": 84}}
        ).encode("utf-8"),
        entry_sha256_by_name={"public_dev.jsonl": digest},
        split_counts={"public_dev": 84},
    )
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_manifest(
            json.dumps({"files": {"public_dev.jsonl": "b" * 64}}).encode("utf-8"),
            entry_sha256_by_name={"public_dev.jsonl": digest},
            split_counts={"public_dev": 84},
        )
    assert excinfo.value.reason is CorpusSemanticReason.manifest_hash_mismatch
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_manifest(
            json.dumps({"counts": {"public_dev": 83}}).encode("utf-8"),
            entry_sha256_by_name={},
            split_counts={"public_dev": 84},
        )
    assert excinfo.value.reason is CorpusSemanticReason.manifest_count_mismatch
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_manifest(
            json.dumps({"nothing": "useful"}).encode("utf-8"),
            entry_sha256_by_name={},
            split_counts={},
        )
    assert excinfo.value.reason is (
        CorpusSemanticReason.manifest_declaration_unrecognized
    )


def test_validation_report_must_declare_a_passing_result() -> None:
    verify_validation_report(json.dumps({"status": "pass"}).encode("utf-8"))
    verify_validation_report(json.dumps({"passed": True}).encode("utf-8"))
    verify_validation_report(json.dumps({"errors": []}).encode("utf-8"))
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_validation_report(json.dumps({"status": "failed"}).encode("utf-8"))
    assert excinfo.value.reason is CorpusSemanticReason.validation_report_not_passing
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_validation_report(json.dumps({"errors": ["broken"]}).encode("utf-8"))
    assert excinfo.value.reason is CorpusSemanticReason.validation_report_not_passing
    with pytest.raises(CorpusSemanticError) as excinfo:
        verify_validation_report(json.dumps({"note": "hi"}).encode("utf-8"))
    assert excinfo.value.reason is CorpusSemanticReason.validation_report_unrecognized


def test_private_manifest_receives_a_keys_only_absence_audit() -> None:
    assert_private_manifest_is_keys_only(
        json.dumps({"case_count": 40, "families": ["kinematics"]}).encode("utf-8")
    )
    for leaking in (
        {"problem_text": "일부 한국어 문제"},
        {"cases": [{"answer": 1.0}]},
        {"note": "한국어 원문이 들어 있음"},
        {"note": "x" * 500},
    ):
        with pytest.raises(CorpusSemanticError) as excinfo:
            assert_private_manifest_is_keys_only(
                json.dumps(leaking, ensure_ascii=False).encode("utf-8")
            )
        assert excinfo.value.reason is (
            CorpusSemanticReason.private_manifest_carries_content
        )


# --------------------------------------------------------------------------
# Preflight orchestration: zero execution, zero cost, fail closed
# --------------------------------------------------------------------------


def test_corpus_preflight_passes_with_zero_execution_and_zero_cost(
    tmp_path: Path,
) -> None:
    path, digest = archive_with(tmp_path)
    result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert result.terminal is PreflightTerminal.passed
    assert result.passed
    assert result.failure_kind is None
    assert result.ledger.zero_execution
    assert result.ledger.runtime_calls == 0
    assert result.ledger.compiler_calls == 0
    assert result.ledger.solver_calls == 0
    assert result.ledger.model_or_provider_calls == 0
    assert result.ledger.measured_cost_usd == 0.0
    assert result.archive_sha256 == digest
    assert result.semantic_evidence is not None
    assert result.semantic_evidence.distribution.supported_accepted == 81


def test_corpus_preflight_runs_with_external_network_blocked(tmp_path: Path) -> None:
    path, digest = archive_with(tmp_path)
    original = socket.socket
    with block_external_network():
        result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert socket.socket is original
    assert result.terminal is PreflightTerminal.passed


@pytest.mark.parametrize(
    ("kwargs", "failure_kind"),
    (
        (
            {"duplicate": ("schema.json", b"{}")},
            Stage7FailureKind.corpus_integrity_failure,
        ),
    ),
)
def test_archive_failure_terminates_as_harness_contract_failure(
    tmp_path: Path, kwargs, failure_kind
) -> None:
    path, digest = archive_with(tmp_path, **kwargs)
    result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert result.terminal is PreflightTerminal.harness_contract_failure
    assert result.failure_kind is failure_kind
    assert result.ledger.zero_execution
    assert result.semantic_evidence is None
    assert result.sanitized_reason is not None
    assert len(result.sanitized_reason) <= 160


def test_semantic_failure_terminates_as_harness_contract_failure(
    tmp_path: Path,
) -> None:
    members = default_members()
    members["public_dev.jsonl"] = _jsonl(build_public_dev_records()[:-1])
    path, digest = archive_with(tmp_path, members=members)
    result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert result.terminal is PreflightTerminal.harness_contract_failure
    assert result.failure_kind is Stage7FailureKind.corpus_reference_issue
    assert result.ledger.zero_execution
    assert result.sanitized_reason == CorpusSemanticReason.split_count_mismatch.value


def test_schema_failure_terminates_as_harness_contract_failure(tmp_path: Path) -> None:
    members = default_members()
    members["schema.json"] = json.dumps({"unknown": True}).encode("utf-8")
    path, digest = archive_with(tmp_path, members=members)
    result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert result.terminal is PreflightTerminal.harness_contract_failure
    assert result.failure_kind is Stage7FailureKind.corpus_integrity_failure
    assert result.ledger.zero_execution


def test_sanitized_failure_reasons_never_carry_corpus_content(tmp_path: Path) -> None:
    members = default_members()
    members["공개_문제_유출.jsonl"] = "질량은 42 kg 이다".encode("utf-8")
    path, digest = archive_with(tmp_path, members=members)
    result = run_corpus_integrity_preflight(path, expected_sha256=digest)
    assert result.sanitized_reason is not None
    assert "질량" not in result.sanitized_reason
    assert "유출" not in result.sanitized_reason
    assert result.sanitized_reason.startswith("unexpected_entry_name")


def test_corpus_modules_cannot_reach_runtime_provider_or_extraction() -> None:
    assert_corpus_modules_are_execution_free(REPOSITORY_ROOT)


def test_raw_corpus_material_is_not_committed_to_the_repository() -> None:
    assert_raw_corpus_is_not_committed(REPOSITORY_ROOT)
