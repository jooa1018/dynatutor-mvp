"""Independently authored Stage 7 corpus fixtures.

Every problem sentence, quote, and number here is written for this test suite.
No public-corpus or held-out problem text is copied, and no fixture is ever
used as a prompt example.  The fixtures mirror the *shape* of the frozen
`dynatutor-ko-corpus-v1.0` schema so the evaluator's binding, integrity, and
scope-mapping rules can be exercised without the authorised archive.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

CORPUS_SCHEMA_VERSION = "dynatutor-ko-corpus-v1.0"

SUPPORTED_FAMILIES: tuple[str, ...] = (
    "constant_acceleration_1d",
    "single_particle_newton",
    "work_energy_speed",
    "impulse_momentum",
    "fixed_axis_rotation",
)
DEFERRED_FAMILIES: tuple[str, ...] = (
    "spring_mass_vibration",
    "relative_acceleration_translation",
    "coriolis_relative_motion",
    "slot_pin_relative_motion",
)

CASE_PROPERTY_NAMES: tuple[str, ...] = (
    "schema_version",
    "case_id",
    "split",
    "language",
    "problem_text",
    "problem_hash",
    "family",
    "difficulty",
    "tags",
    "notes",
    "source_provenance",
    "gold",
)
GOLD_PROPERTY_NAMES: tuple[str, ...] = (
    "parse_status",
    "expected_system_type",
    "phase55_expected_terminal",
    "future_expected_terminal",
    "figure_dependency",
    "entities",
    "motion_segments",
    "events",
    "explicit_facts",
    "relations",
    "assumption_proposals",
    "queries",
    "answers",
    "expected_failure_codes",
)

SCHEMA_DOCUMENT: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DynaTutor Korean Dynamics Corpus Case V1 (fixture)",
    "type": "object",
    "required": [
        "schema_version",
        "case_id",
        "split",
        "language",
        "problem_text",
        "problem_hash",
        "source_provenance",
        "gold",
        "difficulty",
        "tags",
    ],
    "properties": {
        **{name: {"type": "string"} for name in CASE_PROPERTY_NAMES},
        "schema_version": {"const": CORPUS_SCHEMA_VERSION},
        "gold": {
            "type": "object",
            "properties": {name: {"type": "string"} for name in GOLD_PROPERTY_NAMES},
        },
    },
    "additionalProperties": False,
}


def _provenance(chapter: int = 12) -> dict[str, Any]:
    return {
        "basis": "abstract_structure_only",
        "title": "fixture-only structural basis",
        "edition": 12,
        "chapter": chapter,
        "section": "fixture",
        "independently_authored": True,
        "original_problem_text_copied": False,
        "original_numbers_reused": False,
        "original_figures_reused": False,
    }


def build_case(
    *,
    index: int,
    split: str,
    family: str | None,
    future_terminal: str,
    with_answer: bool,
    figure_level: str = "none",
    parse_status: str = "complete",
) -> dict[str, Any]:
    """Build one schema-shaped case with self-consistent evidence."""

    mass = round(1.0 + index * 0.25, 4)
    accel = round(2.0 + index * 0.5, 4)
    problem_text = (
        f"연습 상황 {split} {index}: 수평면 위의 상자에 대하여 "
        f"질량은 {mass} kg 이고 가속도는 {accel} m/s^2 이다. 알짜힘을 구하시오."
    )
    gold: dict[str, Any] = {
        "parse_status": parse_status,
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": future_terminal,
        "figure_dependency": {"level": figure_level, "missing_information": []},
        "entities": [{"role": "box", "kind": "block", "label": "상자"}],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["box"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["box"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            {
                "role": "mass",
                "semantic_key": "mass",
                "raw_value": str(mass),
                "raw_unit": "kg",
                "evidence_quote": f"질량은 {mass} kg",
                "subject_role": "box",
                "segment_role": "motion_1",
                "event_role": None,
                "temporal_role": "timeless",
                "direction": "not_applicable",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
            {
                "role": "acceleration",
                "semantic_key": "acceleration",
                "raw_value": str(accel),
                "raw_unit": "m/s^2",
                "evidence_quote": f"가속도는 {accel} m/s^2",
                "subject_role": "box",
                "segment_role": "motion_1",
                "event_role": None,
                "temporal_role": "timeless",
                "direction": "not_applicable",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
        ],
        "relations": [
            {
                "role": "contact",
                "kind": "contact_with",
                "participant_roles": ["box", "surface"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "net_force",
                "subject_role": "box",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "answers": [],
        "expected_failure_codes": [],
    }
    if with_answer:
        gold["answers"] = [
            {
                "query_role": "q1",
                "numeric": round(mass * accel, 6),
                "unit": "N",
                "tolerance_abs": 0.0001,
                "reference_expression": "m*a",
            }
        ]
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "case_id": f"fx_{split}_{index:04d}",
        "split": split,
        "language": "ko",
        "problem_text": problem_text,
        "problem_hash": hashlib.sha256(problem_text.encode("utf-8")).hexdigest(),
        "family": family,
        "difficulty": 2,
        "tags": ["fixture"],
        "notes": [],
        "source_provenance": _provenance(),
        "gold": gold,
    }


def build_public_dev_records() -> list[dict[str, Any]]:
    """84 development cases: 72 in-scope supported plus 12 deferred families."""

    records = [
        build_case(
            index=index,
            split="public_dev",
            family=SUPPORTED_FAMILIES[index % len(SUPPORTED_FAMILIES)],
            future_terminal="accepted",
            with_answer=True,
        )
        for index in range(72)
    ]
    records.extend(
        build_case(
            index=100 + offset,
            split="public_dev",
            # The corpus still declares "accepted"; current course scope is what
            # withdraws answer authority for these four families.
            family=DEFERRED_FAMILIES[offset % len(DEFERRED_FAMILIES)],
            future_terminal="accepted",
            with_answer=True,
        )
        for offset in range(12)
    )
    return records


def build_public_adversarial_records() -> list[dict[str, Any]]:
    """16 adversarial cases: 9 supported plus the 2/2/2/1 blocked classes."""

    plan: list[tuple[str, bool, str, str]] = (
        [("accepted", True, "none", "complete")] * 9
        + [("needs_figure", False, "required", "needs_figure")] * 2
        + [("needs_confirmation", False, "none", "ambiguous")] * 2
        + [("solver_gap", False, "none", "unsupported")] * 2
        + [("insufficient_information", False, "none", "insufficient_information")]
    )
    return [
        build_case(
            index=index,
            split="public_adversarial",
            family=SUPPORTED_FAMILIES[index % len(SUPPORTED_FAMILIES)],
            future_terminal=terminal,
            with_answer=with_answer,
            figure_level=figure_level,
            parse_status=parse_status,
        )
        for index, (terminal, with_answer, figure_level, parse_status) in enumerate(plan)
    ]


def jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return (
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"
    ).encode("utf-8")


def schema_bytes() -> bytes:
    return json.dumps(SCHEMA_DOCUMENT, ensure_ascii=False).encode("utf-8")


def default_members() -> dict[str, bytes]:
    return {
        "public_dev.jsonl": jsonl_bytes(build_public_dev_records()),
        "public_adversarial.jsonl": jsonl_bytes(build_public_adversarial_records()),
        "schema.json": schema_bytes(),
    }


def write_plain_archive(path: Path, members: dict[str, bytes]) -> str:
    """Write a minimal well-formed archive and return its SHA-256."""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()
