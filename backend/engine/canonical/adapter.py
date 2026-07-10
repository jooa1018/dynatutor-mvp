from __future__ import annotations

import copy
from dataclasses import fields
import hashlib
import json
import math
import re
from typing import Any

from engine.canonical.models import (
    AssumptionRecord,
    CanonicalProblemV2,
    ExtractedFact,
    ParseCandidate,
    SystemTypeCandidate,
)
from engine.models import CanonicalProblem, Quantity


_DIMENSIONS = {
    "": "dimensionless",
    "kg": "mass",
    "m": "length",
    "s": "time",
    "m/s": "velocity",
    "m/s^2": "acceleration",
    "n": "force",
    "j": "energy",
    "n/m": "stiffness",
    "n*m": "torque",
    "kg*m^2": "moment_of_inertia",
    "deg": "angle",
    "rad": "angle",
    "rad/s": "angular_velocity",
    "rad/s^2": "angular_acceleration",
    "hz": "frequency",
}

_CONDITION_PATTERNS: list[tuple[str, str, str]] = [
    ("air_resistance_ignored", r"공기\s*저항(?:을|은|이)?\s*(?:무시|없)|air\s+resistance\s+(?:is\s+)?(?:ignored|neglected)", "explicit"),
    ("no_friction", r"마찰(?:이|은|을)?\s*(?:없|무시)|frictionless|\bsmooth\b|매끈|매끄러운", "explicit"),
    ("no_slip", r"미끄러지지\s*않|미끄럼\s*없이|no\s+slip|without\s+slipping|순수\s*구름", "explicit"),
    ("massless_string", r"질량\s*(?:이\s*)?없는\s*(?:줄|실|끈)|가벼운\s*(?:줄|실|끈)|massless\s+(?:string|rope)", "explicit"),
    ("inextensible_string", r"늘어나지\s*않는\s*(?:줄|실|끈)|inextensible\s+(?:string|rope)", "explicit"),
    ("frictionless_pulley", r"도르래(?:의|\s*축)?\s*마찰(?:을|은|이)?\s*(?:무시|없)|frictionless\s+pulley", "explicit"),
    ("perfectly_inelastic", r"완전\s*비탄성|붙어서|한\s*덩어리|perfectly\s+inelastic|stick\s+together", "explicit"),
    ("elastic_collision", r"완전\s*탄성|elastic\s+collision", "explicit"),
    ("initially_at_rest", r"정지\s*(?:상태|해\s*있|하여|에서)|가만히\s*있|starts?\s+from\s+rest", "explicit"),
]

_LABEL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<label>theta|omega0|alpha|tau|mu_s|mu_k|m1|m2|v1f|v2f|v0|vf|v1|v2|"
    r"rddot|rdot|thetaddot|thetadot|m|a|t|s|F|k|x|h|g|I|R|r|e|W)"
    r"(?![A-Za-z0-9_])\s*(?:=|:)\s*"
    r"(?P<value>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(?P<unit>kg\s*\*?\s*m\^?2|kgm\^?2|km\s*/\s*h|km/h|cm/s(?:(?:\^?2|2|²))?|"
    r"m/s(?:(?:\^?2|2|²))?|rad/s(?:(?:\^?2|2|²))?|N\s*\*\s*m|N/m|N|J|kg|cm|m|s|deg|도|°|Hz)?",
    re.IGNORECASE,
)


def dimension_for_unit(unit: str | None) -> str:
    if unit is None:
        return "dimensionless"
    key = (
        unit.strip()
        .replace("²", "^2")
        .replace(" ", "")
        .replace("kgm", "kg*m")
        .replace("Nm", "N*m")
        .lower()
    )
    if key == "m/s2":
        key = "m/s^2"
    if key == "rad/s2":
        key = "rad/s^2"
    if key == "kg*m2":
        key = "kg*m^2"
    return _DIMENSIONS.get(key, "unknown")


def _stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


_SUBJECT_BINDINGS: dict[str, tuple[str, str]] = {
    "m1": ("object_1", "m"),
    "v1": ("object_1", "v"),
    "v1f": ("object_1", "v_after"),
    "m2": ("object_2", "m"),
    "v2": ("object_2", "v"),
    "v2f": ("object_2", "v_after"),
    "Ip": ("pulley", "I"),
    "Rp": ("pulley", "R"),
    "vA": ("point_A", "vA"),
    "aA": ("point_A", "aA"),
    "vAx": ("point_A", "vAx"),
    "vAy": ("point_A", "vAy"),
    "aAx": ("point_A", "aAx"),
    "aAy": ("point_A", "aAy"),
    "vB": ("point_B", "vB"),
    "aB": ("point_B", "aB"),
    "vBx": ("point_B", "vBx"),
    "vBy": ("point_B", "vBy"),
    "aBx": ("point_B", "aBx"),
    "aBy": ("point_B", "aBy"),
    "rBAx": ("point_B", "rBAx"),
    "rBAy": ("point_B", "rBAy"),
    "A": ("oscillator", "A"),
    "k": ("oscillator", "k"),
    "x": ("oscillator", "x"),
}
_SYSTEM_KEYS = {"g", "theta", "e", "mu", "mu_s", "mu_k", "W", "tau", "omega", "omega0", "alpha"}
_BODY_KEYS = {
    "m", "v", "v0", "vf", "F", "a", "t", "s", "h", "h0", "yf",
    "I", "R", "r", "rdot", "rddot", "thetadot", "thetaddot",
    "vrel", "arel",
}
# Background classification is discourse-based. Ordinary actors and devices such
# as students, observers, teachers, friends, and scales are not background merely
# because their noun occurs near a fact.
_BACKGROUND_MARKERS = (
    "참고로",
    "무관하",
    "관계없",
    "사용하지 않",
    "for reference",
    "irrelevant",
    "unrelated",
    "do not use",
)


def _valid_source_span(raw_text: str, quantity: Quantity) -> bool:
    span = quantity.source_span
    if span is None:
        return False
    start, end = span
    if start < 0 or end <= start or end > len(raw_text):
        return False
    matched = quantity.matched_text
    return bool(matched) and raw_text[start:end] == matched


def _span_context(raw_text: str, span: tuple[int, int] | None) -> str:
    if span is None:
        return ""
    start, end = span
    boundaries = (".", "!", "?", "\n", "\r")
    left = max(raw_text.rfind(boundary, 0, start) for boundary in boundaries)
    right_candidates = [
        position
        for boundary in boundaries
        if (position := raw_text.find(boundary, end)) >= 0
    ]
    right = min(right_candidates) if right_candidates else len(raw_text)
    return raw_text[left + 1:right]


def _subject_and_symbol(
    canonical: CanonicalProblem,
    key: str,
    quantity: Quantity,
) -> tuple[str, str]:
    if _valid_source_span(canonical.raw_text, quantity):
        context = _span_context(canonical.raw_text, quantity.source_span)
        if any(marker in context for marker in _BACKGROUND_MARKERS):
            return "background", key
    if key in _SUBJECT_BINDINGS:
        return _SUBJECT_BINDINGS[key]
    if key in _SYSTEM_KEYS:
        return "system", key
    if key in _BODY_KEYS:
        return "body", key
    return "unbound", key


def _quantity_status(
    canonical: CanonicalProblem,
    quantity: Quantity,
) -> tuple[str, str, float]:
    hint = quantity.provenance_hint
    source = quantity.source_text or ""
    has_raw_evidence = _valid_source_span(canonical.raw_text, quantity)

    if hint == "user_confirmation":
        return "inferred", "user_confirmation", 1.0
    if hint == "domain_default" or (hint is None and "기본값" in source):
        return "defaulted", "domain_default", 0.95
    if hint == "compatibility_alias":
        return "inferred", "compatibility_alias", 0.85
    if hint == "unit_normalization":
        return "normalized", "unit_normalization", 1.0 if has_raw_evidence else 0.7
    if hint == "domain_rule":
        return "inferred", "domain_rule", 0.85 if has_raw_evidence else 0.75
    if has_raw_evidence:
        return "explicit", "text_extraction", 1.0
    return "inferred", "legacy_unverified", 0.5

def _normalization_alternative(quantity: Quantity) -> dict[str, Any] | None:
    evidence = quantity.normalization_evidence
    if not evidence:
        return None
    source_value = evidence.get("source_value")
    source_unit = evidence.get("source_unit")
    if source_value is None or source_unit is None:
        return None
    return {
        "value": float(source_value),
        "unit": str(source_unit).replace(" ", ""),
        "relation": "source_representation",
    }


def _quantity_fact(canonical: CanonicalProblem, key: str, quantity: Quantity) -> ExtractedFact:
    status, provenance, confidence = _quantity_status(canonical, quantity)
    subject_id, symbol = _subject_and_symbol(canonical, key, quantity)
    span = quantity.source_span if _valid_source_span(canonical.raw_text, quantity) else None
    if subject_id == "background":
        status = "inferred"
        provenance = "background_context"
        confidence = min(confidence, 0.2)

    alternatives: list[dict[str, Any]] = []
    source_representation = _normalization_alternative(quantity)
    if source_representation:
        alternatives.append(source_representation)

    direction = canonical.force_direction if key in {"F", "a"} else None
    subject_evidence = dict(quantity.subject_evidence)
    subject_evidence.update(
        {
            "binding_rule": "exact_compatibility_key",
            "resolved_subject_id": subject_id,
        }
    )
    extraction_evidence: dict[str, Any] = {
        "subject_evidence": subject_evidence,
    }
    if span is not None:
        extraction_evidence["matched_raw_text"] = canonical.raw_text[span[0]:span[1]]
    if quantity.normalization_evidence is not None:
        extraction_evidence["normalization_evidence"] = dict(quantity.normalization_evidence)

    identity = {
        "kind": "quantity",
        "subject_id": subject_id,
        "symbol": symbol,
        "compatibility_key": key,
        "value": quantity.value,
        "unit": quantity.unit,
        "source_span": span,
        "status": status,
        "provenance": provenance,
    }
    return ExtractedFact(
        fact_id=_stable_id("fact", identity),
        kind="quantity",
        subject_id=subject_id,
        symbol=symbol,
        value=quantity.value,
        unit=quantity.unit,
        dimension=dimension_for_unit(quantity.unit),
        direction=direction,
        source_text=quantity.source_text,
        source_span=span,
        provenance=provenance,
        confidence=confidence,
        status=status,
        alternatives=alternatives,
        compatibility_key=key,
        extraction_evidence=extraction_evidence,
    )

def _condition_facts(canonical: CanonicalProblem) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    raw = canonical.raw_text
    for symbol, pattern, declared_status in _CONDITION_PATTERNS:
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            continue
        matched_text = match.group(0)
        status = declared_status
        provenance = "explicit_text"
        confidence = 1.0
        if symbol == "no_friction" and re.search(r"\bsmooth\b|매끈|매끄러운", matched_text, re.IGNORECASE):
            status = "normalized"
            provenance = "domain_rule"
            confidence = 0.95
        identity = {
            "kind": "condition",
            "subject_id": "system",
            "symbol": symbol,
            "value": True,
            "source_span": (match.start(), match.end()),
        }
        facts.append(
            ExtractedFact(
                fact_id=_stable_id("fact", identity),
                kind="condition",
                subject_id="system",
                symbol=symbol,
                value=True,
                unit=None,
                dimension="dimensionless",
                direction=None,
                source_text=matched_text,
                source_span=(match.start(), match.end()),
                provenance=provenance,
                confidence=confidence,
                status=status,
                alternatives=[],
                compatibility_key=None,
                extraction_evidence={
                    "matched_raw_text": raw[match.start():match.end()],
                    "subject_evidence": {
                        "binding_rule": "condition_pattern",
                        "resolved_subject_id": "system",
                    },
                },
            )
        )
    return facts


def _normalize_labeled_value(label: str, value: float, unit: str | None) -> tuple[float, str | None]:
    normalized_unit = (unit or "").replace(" ", "").replace("²", "^2").lower()
    if normalized_unit in {"km/h", "km/h"}:
        return value / 3.6, "m/s"
    if normalized_unit in {"cm/s^2", "cm/s2"}:
        return value / 100.0, "m/s^2"
    if normalized_unit == "cm":
        return value / 100.0, "m"
    if normalized_unit in {"도", "°", "deg"}:
        return value, "deg"
    if normalized_unit in {"m/s2", "m/s^2"}:
        return value, "m/s^2"
    if normalized_unit in {"rad/s2", "rad/s^2"}:
        return value, "rad/s^2"
    if normalized_unit in {"kgm^2", "kg*m^2", "kg*m2"}:
        return value, "kg*m^2"
    if normalized_unit in {"n*m", "n*m"}:
        return value, "N*m"
    return value, unit.replace(" ", "") if unit else None


def _semantic_equal(
    left: tuple[float, str | None],
    right: tuple[float, str | None],
) -> bool:
    return (
        math.isclose(left[0], right[0], rel_tol=1e-12, abs_tol=1e-12)
        and (left[1] == right[1] or left[1] is None or right[1] is None)
    )


def _refresh_fact_id(fact: ExtractedFact) -> None:
    fact.fact_id = _stable_id(
        "fact",
        {
            "kind": fact.kind,
            "subject_id": fact.subject_id,
            "symbol": fact.symbol,
            "compatibility_key": fact.compatibility_key,
            "value": fact.value,
            "unit": fact.unit,
            "source_span": fact.source_span,
            "status": fact.status,
            "provenance": fact.provenance,
            "alternatives": fact.alternatives,
        },
    )


def _apply_conflicts(
    raw_text: str,
    facts: list[ExtractedFact],
) -> tuple[list[str], list[str]]:
    occurrences: dict[str, list[dict[str, Any]]] = {}
    for match in _LABEL_PATTERN.finditer(raw_text):
        label = match.group("label")
        value = float(match.group("value").replace(",", ""))
        raw_unit = match.group("unit") or None
        normalized_value, normalized_unit = _normalize_labeled_value(label, value, raw_unit)
        occurrences.setdefault(label, []).append(
            {
                "value": value,
                "unit": raw_unit.replace(" ", "") if raw_unit else None,
                "normalized_value": normalized_value,
                "normalized_unit": normalized_unit,
                "source_text": match.group(0),
                "source_span": [match.start(), match.end()],
                "relation": "explicit_occurrence",
            }
        )

    unresolved: list[str] = []
    resolved: list[str] = []
    by_key = {fact.compatibility_key: fact for fact in facts if fact.compatibility_key}
    for label, items in occurrences.items():
        fact = by_key.get(label)
        if fact is None or fact.value is None:
            continue

        semantic_values: list[tuple[float, str | None]] = []
        for item in items:
            pair = (float(item["normalized_value"]), item["normalized_unit"])
            if not any(_semantic_equal(existing, pair) for existing in semantic_values):
                semantic_values.append(pair)

        fact_pair = _normalize_labeled_value(
            label,
            float(fact.value),
            fact.unit,
        )
        fact_semantic = (float(fact_pair[0]), fact_pair[1])
        fact_matches_occurrence = any(
            _semantic_equal(fact_semantic, pair) for pair in semantic_values
        )
        has_conflict = len(semantic_values) > 1 or not fact_matches_occurrence
        if len(items) > 1 or has_conflict:
            fact.alternatives = items
        if not has_conflict:
            continue

        rendered = ", ".join(
            f"{item['value']} {item['unit'] or ''}".strip() for item in items
        )
        if fact.provenance == "user_confirmation":
            fact.status = "inferred"
            fact.confidence = 1.0
            fact.extraction_evidence["conflict_resolution"] = {
                "resolution": "user_confirmation",
                "selected_value": fact.value,
                "selected_unit": fact.unit,
                "raw_candidates": items,
            }
            resolved.append(
                f"{label} conflict resolved by user confirmation: "
                f"{fact.value} {fact.unit or ''}; raw candidates: {rendered}"
            )
        else:
            fact.status = "conflicting"
            fact.provenance = "conflict_detection"
            fact.confidence = min(fact.confidence, 0.5)
            unresolved.append(
                f"{label} has conflicting explicit values: {rendered}"
            )

    for fact in facts:
        _refresh_fact_id(fact)
    return unresolved, resolved

def _assumption_kind(reason: str) -> str:
    mapping = [
        ("중력가속도", "gravity"),
        ("질점", "particle_model"),
        ("마찰", "friction"),
        ("줄", "string_model"),
        ("도르래", "pulley_model"),
        ("공기저항", "air_resistance"),
        ("가속도", "kinematics"),
        ("회전", "rotation"),
        ("감쇠", "damping"),
        ("외력", "external_force"),
        ("에너지", "energy_model"),
        ("좌표", "coordinate_frame"),
        ("Coriolis", "rotating_frame"),
        ("코리올리", "rotating_frame"),
    ]
    for needle, kind in mapping:
        if needle in reason:
            return kind
    return "modeling"


def _explicit_condition_for_assumption(reason: str) -> str | None:
    if "공기저항" in reason:
        return "air_resistance_ignored"
    if "마찰력 없음" in reason or "마찰 없음" in reason:
        return "no_friction"
    if "미끄러지지" in reason or "순수 구름" in reason:
        return "no_slip"
    if "줄은 질량" in reason or "질량 없는 줄" in reason:
        return "massless_string"
    if "줄" in reason and "늘어나지" in reason:
        return "inextensible_string"
    if "도르래" in reason and "마찰" in reason:
        return "frictionless_pulley"
    return None


def _assumption_records(canonical: CanonicalProblem, facts: list[ExtractedFact]) -> list[AssumptionRecord]:
    explicit_conditions = {
        fact.symbol for fact in facts if fact.kind == "condition" and fact.status in {"explicit", "normalized"}
    }
    fact_by_key = {fact.compatibility_key: fact for fact in facts if fact.compatibility_key}
    records: list[AssumptionRecord] = []
    for reason in canonical.assumptions:
        explicit_condition = _explicit_condition_for_assumption(reason)
        if explicit_condition in explicit_conditions:
            continue
        if "중력가속도" in reason:
            gravity = fact_by_key.get("g")
            if gravity and gravity.status != "defaulted":
                continue
        if reason.startswith("[사용자 확인]"):
            source = "user_confirmation"
            confidence = 1.0
            value: Any = reason.removeprefix("[사용자 확인] ").strip()
        elif "중력가속도" in reason:
            source = "domain_default"
            confidence = 0.95
            value = canonical.knowns.get("g").value if canonical.knowns.get("g") else 9.81
        else:
            source = "solver_default"
            confidence = 0.75
            value = reason
        kind = _assumption_kind(reason)
        identity = {"kind": kind, "value": value, "reason": reason, "source": source}
        records.append(
            AssumptionRecord(
                assumption_id=_stable_id("assumption", identity),
                kind=kind,
                value=value,
                reason=reason,
                source=source,
                confidence=confidence,
                user_visible=True,
            )
        )
    return records


def _candidate_specs(canonical: CanonicalProblem) -> list[tuple[str, str | None, float, str]]:
    confidence_score = {"높음": 0.95, "보통": 0.7, "낮음": 0.4}.get(canonical.confidence, 0.5)
    specs = [
        (
            canonical.system_type,
            canonical.subtype,
            confidence_score,
            "legacy cascade selection preserved as the primary compatibility candidate",
        )
    ]
    if canonical.system_type == "ambiguous_pulley":
        specs.extend(
            [
                ("pulley_atwood", None, 0.6, "two masses and a pulley are present; placement is unresolved"),
                ("pulley_table_hanging", None, 0.6, "one mass may be on a table and the other hanging"),
                ("pulley_incline_hanging", None, 0.6, "one mass may be on an incline and the other hanging"),
            ]
        )
    elif canonical.system_type == "incline_hanging_candidate":
        specs.extend(
            [
                ("pulley_incline_hanging", None, 0.65, "the two bodies may share a pulley string"),
                ("particle_on_incline", canonical.subtype, 0.55, "the hanging body may be unrelated background"),
            ]
        )
    elif canonical.system_type == "particle_on_incline" and canonical.subtype == "unknown_friction":
        specs.extend(
            [
                ("particle_on_incline", "no_friction", 0.6, "friction may be absent"),
                ("particle_on_incline", "with_friction", 0.6, "friction may be present"),
            ]
        )
    flags = canonical.flags or {}
    if flags.get("spring") and flags.get("incline"):
        specs.extend(
            [
                ("spring_energy", None, 0.5, "spring-energy interpretation"),
                ("particle_on_incline", canonical.subtype, 0.5, "incline-dynamics interpretation"),
            ]
        )
    if flags.get("collision") and flags.get("incline"):
        specs.extend(
            [
                ("collision_1d", None, 0.5, "collision-stage interpretation"),
                ("particle_on_incline", canonical.subtype, 0.5, "post-collision incline interpretation"),
            ]
        )
    unique: list[tuple[str, str | None, float, str]] = []
    seen: set[tuple[str, str | None]] = set()
    for spec in specs:
        key = (spec[0], spec[1])
        if key not in seen:
            seen.add(key)
            unique.append(spec)
    return unique


def _parse_candidates(canonical: CanonicalProblem, facts: list[ExtractedFact], conflicts: list[str]) -> list[ParseCandidate]:
    fact_ids = sorted(fact.fact_id for fact in facts)
    candidates: list[ParseCandidate] = []
    for index, (system_type, subtype, score, reason) in enumerate(_candidate_specs(canonical), start=1):
        system_candidate = SystemTypeCandidate(
            system_type=system_type,
            subtype=subtype,
            score=score,
            reason=reason,
        )
        identity = {
            "system_type": system_type,
            "subtype": subtype,
            "facts": fact_ids,
            "score": score,
        }
        warnings = [] if index == 1 else ["alternative interpretation retained; not selected by the legacy cascade"]
        candidates.append(
            ParseCandidate(
                candidate_id=_stable_id("candidate", identity),
                facts=fact_ids,
                system_type_candidates=[system_candidate],
                score=score,
                warnings=warnings,
                missing_info=list(canonical.missing_info),
                conflicts=list(conflicts),
            )
        )
    return candidates


def _legacy_view(canonical: CanonicalProblem) -> dict[str, Any]:
    view: dict[str, Any] = {}
    for field_info in fields(CanonicalProblem):
        name = field_info.name
        if name == "canonical_v2":
            continue
        value = getattr(canonical, name)
        if name == "knowns":
            view[name] = {
                key: {
                    "symbol": quantity.symbol,
                    "value": quantity.value,
                    "unit": quantity.unit,
                    "source_text": quantity.source_text,
                    "source_span": quantity.source_span,
                    "matched_text": quantity.matched_text,
                    "provenance_hint": quantity.provenance_hint,
                    "subject_evidence": copy.deepcopy(quantity.subject_evidence),
                    "normalization_evidence": copy.deepcopy(quantity.normalization_evidence),
                }
                for key, quantity in value.items()
            }
        else:
            view[name] = copy.deepcopy(value)
    return view


def build_canonical_v2(
    canonical: CanonicalProblem,
    *,
    normalized_text: str | None = None,
) -> CanonicalProblemV2:
    if normalized_text is None:
        from engine.extraction.normalizer import normalize

        normalized_text = normalize(canonical.raw_text)

    facts = [_quantity_fact(canonical, key, quantity) for key, quantity in canonical.knowns.items()]
    facts.extend(_condition_facts(canonical))
    conflicts, resolved_conflicts = _apply_conflicts(canonical.raw_text, facts)
    assumptions = _assumption_records(canonical, facts)
    parse_candidates = _parse_candidates(canonical, facts, conflicts)
    warnings = [
        f"explicit fact has no raw source span: {fact.fact_id}"
        for fact in facts
        if fact.status == "explicit" and fact.provenance == "text_extraction" and fact.source_span is None
    ]
    return CanonicalProblemV2(
        schema_version="2.0",
        raw_text=canonical.raw_text,
        normalized_text=normalized_text,
        language=canonical.language,
        system_type=canonical.system_type,
        subtype=canonical.subtype,
        facts=facts,
        assumptions=assumptions,
        parse_candidates=parse_candidates,
        requested_outputs=list(canonical.requested_outputs),
        flags=dict(canonical.flags),
        objects=copy.deepcopy(canonical.objects),
        missing_info=list(canonical.missing_info),
        conflicts=conflicts,
        warnings=warnings,
        legacy_view=_legacy_view(canonical),
        resolved_conflicts=resolved_conflicts,
    )


def attach_canonical_v2(
    canonical: CanonicalProblem,
    *,
    normalized_text: str | None = None,
) -> CanonicalProblemV2:
    canonical.canonical_v2 = build_canonical_v2(canonical, normalized_text=normalized_text)
    return canonical.canonical_v2


def to_legacy_problem(canonical_v2: CanonicalProblemV2) -> CanonicalProblem:
    view = canonical_v2.legacy_view
    kwargs: dict[str, Any] = {}
    for field_info in fields(CanonicalProblem):
        name = field_info.name
        if name == "canonical_v2":
            continue
        if name not in view:
            continue
        if name == "knowns":
            kwargs[name] = {
                key: Quantity(
                    symbol=value["symbol"],
                    value=value.get("value"),
                    unit=value.get("unit"),
                    source_text=value.get("source_text"),
                    source_span=(
                        tuple(value["source_span"])
                        if value.get("source_span") is not None
                        else None
                    ),
                    matched_text=value.get("matched_text"),
                    provenance_hint=value.get("provenance_hint"),
                    subject_evidence=dict(value.get("subject_evidence") or {}),
                    normalization_evidence=(
                        dict(value["normalization_evidence"])
                        if value.get("normalization_evidence") is not None
                        else None
                    ),
                )
                for key, value in (view.get("knowns") or {}).items()
            }
        else:
            kwargs[name] = copy.deepcopy(view[name])
    legacy = CanonicalProblem(**kwargs)
    legacy.canonical_v2 = canonical_v2
    return legacy
