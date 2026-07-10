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
    ("no_friction", r"마찰(?:이|은|을)?\s*(?:없|무시)|마찰\s*업는|frictionless|\bsmooth\b|매끈|매끄러운|매끄런", "explicit"),
    ("no_slip", r"미끄러지지\s*않|미끄럼\s*없이|no\s+slip|without\s+slipping|순수\s*구름", "explicit"),
    ("massless_string", r"질량\s*(?:이\s*)?없는\s*(?:줄|실|끈)|가벼운\s*(?:줄|실|끈)|massless\s+(?:string|rope)", "explicit"),
    ("inextensible_string", r"늘어나지\s*않는\s*(?:줄|실|끈)|inextensible\s+(?:string|rope)", "explicit"),
    ("frictionless_pulley", r"도르래(?:의|\s*축)?\s*마찰(?:을|은|이)?\s*(?:무시|없)|frictionless\s+pulley", "explicit"),
    ("perfectly_inelastic", r"완전\s*비탄성|붙어서|붙는\s*충돌|붙어\s*움직|한\s*덩어리|perfectly\s+inelastic|stick\s+together", "explicit"),
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


def _subject_and_symbol(key: str) -> tuple[str, str]:
    if key in {"m1", "v1", "v1f"}:
        return "object_1", {"m1": "m", "v1": "v", "v1f": "v_after"}[key]
    if key in {"m2", "v2", "v2f"}:
        return "object_2", {"m2": "m", "v2": "v", "v2f": "v_after"}[key]
    if key in {"Ip", "Rp"}:
        return "pulley", {"Ip": "I", "Rp": "R"}[key]
    if key.endswith("A") or key in {"vAx", "vAy", "aAx", "aAy"}:
        return "point_A", key
    if key.endswith("B") or key in {"vBx", "vBy", "aBx", "aBy", "rBAx", "rBAy"}:
        return "point_B", key
    if key in {"g", "theta", "e", "mu", "mu_s", "mu_k", "W"}:
        return "system", key
    return "body", key


def _quantity_status(quantity: Quantity) -> tuple[str, str, float]:
    source = quantity.source_text or ""
    lower = source.lower()
    if lower.startswith("사용자 입력"):
        return "explicit", "user_confirmation", 1.0
    if "기본값" in source:
        return "defaulted", "domain_default", 0.95
    if "충돌 진행 물체" in source:
        return "inferred", "compatibility_alias", 0.9
    if "→ m/s" in source or "→ m/s²" in source:
        return "normalized", "unit_normalization", 1.0
    if "단위 생략" in source:
        return "inferred", "domain_rule", 0.8
    if "→" in source or "inferred" in lower or "정지" in source and quantity.value == 0:
        return "inferred", "domain_rule", 0.9
    return "explicit", "text_extraction", 1.0


def _source_span(raw_text: str, source_text: str | None) -> tuple[int, int] | None:
    if not source_text or source_text.startswith("기본값") or source_text.startswith("사용자 입력"):
        return None
    candidates = [source_text]
    for separator in (" →", " ("):
        candidates.extend(item.split(separator, 1)[0].strip() for item in list(candidates) if separator in item)
    for candidate in sorted(set(candidates), key=len, reverse=True):
        if not candidate:
            continue
        start = raw_text.lower().find(candidate.lower())
        if start >= 0:
            return start, start + len(candidate)
        flexible = re.escape(candidate).replace(r"\ ", r"\s*")
        match = re.search(flexible, raw_text, re.IGNORECASE)
        if match:
            return match.start(), match.end()
    return None


def _source_representation(source_text: str | None) -> dict[str, Any] | None:
    if not source_text:
        return None
    match = re.search(
        r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(km\s*/\s*h|km/h|cm/s(?:\^?2|2|²))",
        source_text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "value": float(match.group(1).replace(",", "")),
        "unit": match.group(2).replace(" ", ""),
        "relation": "source_representation",
    }




def _raw_normalization_evidence(
    raw_text: str,
    key: str,
    quantity: Quantity,
) -> tuple[tuple[int, int], str, dict[str, Any]] | None:
    """Recover the pre-normalization representation from the original prompt."""

    if quantity.value is None:
        return None
    specifications: list[tuple[set[str], str, str, float, str]] = [
        (
            {"v0", "vf", "v", "v1", "v2", "vA", "vB", "vrel", "rdot"},
            r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*km\s*/\s*(?:h|hr|hour|시)",
            "km/h",
            1.0 / 3.6,
            "m/s",
        ),
        (
            {"a", "aA", "aB", "arel", "rddot"},
            r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*cm\s*/\s*s(?:\^?2|2|²)",
            "cm/s^2",
            0.01,
            "m/s^2",
        ),
        (
            {"m", "m1", "m2"},
            r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*g(?![A-Za-z/])",
            "g",
            0.001,
            "kg",
        ),
        (
            {"h", "h0", "yf", "s", "x", "R", "r", "Rp"},
            r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*cm(?![A-Za-z/])",
            "cm",
            0.01,
            "m",
        ),
    ]
    for keys, pattern, source_unit, factor, target_unit in specifications:
        if key not in keys or quantity.unit != target_unit:
            continue
        for match in re.finditer(pattern, raw_text, re.IGNORECASE):
            source_value = float(match.group(1).replace(",", ""))
            if math.isclose(
                source_value * factor,
                float(quantity.value),
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                source_text = match.group(0)
                return (
                    (match.start(), match.end()),
                    f"{source_text} → {quantity.value:g} {target_unit}",
                    {
                        "value": source_value,
                        "unit": source_unit,
                        "relation": "source_representation",
                    },
                )
    return None

def _quantity_fact(canonical: CanonicalProblem, key: str, quantity: Quantity) -> ExtractedFact:
    status, provenance, confidence = _quantity_status(quantity)
    subject_id, symbol = _subject_and_symbol(key)
    span = _source_span(canonical.raw_text, quantity.source_text)
    source_text = quantity.source_text
    alternatives: list[dict[str, Any]] = []
    source_representation = _source_representation(quantity.source_text)
    if source_representation:
        alternatives.append(source_representation)
    raw_normalization = _raw_normalization_evidence(canonical.raw_text, key, quantity)
    if raw_normalization is not None:
        span, source_text, raw_representation = raw_normalization
        status = "normalized"
        provenance = "unit_normalization"
        confidence = 1.0
        if raw_representation not in alternatives:
            alternatives.append(raw_representation)
    direction = canonical.force_direction if key in {"F", "a"} else None
    identity = {
        "kind": "quantity",
        "subject_id": subject_id,
        "symbol": symbol,
        "compatibility_key": key,
        "value": quantity.value,
        "unit": quantity.unit,
        "source_span": span,
        "status": status,
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
        source_text=source_text,
        source_span=span,
        provenance=provenance,
        confidence=confidence,
        status=status,
        alternatives=alternatives,
        compatibility_key=key,
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


def _apply_conflicts(raw_text: str, facts: list[ExtractedFact]) -> list[str]:
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

    conflicts: list[str] = []
    by_key = {fact.compatibility_key: fact for fact in facts if fact.compatibility_key}
    for label, items in occurrences.items():
        if len(items) < 2 or label not in by_key:
            continue
        semantic_values: list[tuple[float, str | None]] = []
        for item in items:
            pair = (float(item["normalized_value"]), item["normalized_unit"])
            if not any(
                existing_unit == pair[1] and math.isclose(existing_value, pair[0], rel_tol=1e-12, abs_tol=1e-12)
                for existing_value, existing_unit in semantic_values
            ):
                semantic_values.append(pair)
        fact = by_key[label]
        fact.alternatives = items
        if len(semantic_values) > 1:
            fact.status = "conflicting"
            fact.provenance = "conflict_detection"
            fact.confidence = min(fact.confidence, 0.5)
            rendered = ", ".join(f"{item['value']} {item['unit'] or ''}".strip() for item in items)
            conflicts.append(f"{label} has conflicting explicit values: {rendered}")
    return conflicts


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
    conflicts = _apply_conflicts(canonical.raw_text, facts)
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
                )
                for key, value in (view.get("knowns") or {}).items()
            }
        else:
            kwargs[name] = copy.deepcopy(view[name])
    legacy = CanonicalProblem(**kwargs)
    legacy.canonical_v2 = canonical_v2
    return legacy
