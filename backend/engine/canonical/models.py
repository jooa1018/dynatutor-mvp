from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


FACT_STATUSES = frozenset(
    {"explicit", "normalized", "inferred", "assumed", "defaulted", "conflicting"}
)


def _canonicalize(value: Any) -> Any:
    """Return a JSON-safe representation whose collection order is stable."""

    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set)):
        items = [_canonicalize(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
    return value


@dataclass
class ExtractedFact:
    fact_id: str
    kind: str
    subject_id: str
    symbol: str
    value: Any
    unit: str | None
    dimension: str
    direction: str | None
    source_text: str | None
    source_span: tuple[int, int] | None
    provenance: str
    confidence: float
    status: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    compatibility_key: str | None = None

    def __post_init__(self) -> None:
        if self.status not in FACT_STATUSES:
            raise ValueError(f"unsupported fact status: {self.status}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("fact confidence must be between 0 and 1")
        if self.source_span is not None:
            start, end = self.source_span
            if start < 0 or end < start:
                raise ValueError("source_span must be a valid half-open range")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedFact":
        values = dict(data)
        span = values.get("source_span")
        values["source_span"] = tuple(span) if span is not None else None
        values["alternatives"] = [dict(item) for item in values.get("alternatives") or []]
        return cls(**values)


@dataclass
class AssumptionRecord:
    assumption_id: str
    kind: str
    value: Any
    reason: str
    source: str
    confidence: float
    user_visible: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("assumption confidence must be between 0 and 1")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssumptionRecord":
        return cls(**dict(data))


@dataclass
class SystemTypeCandidate:
    system_type: str
    subtype: str | None
    score: float
    reason: str

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("candidate score must be between 0 and 1")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemTypeCandidate":
        return cls(**dict(data))


@dataclass
class ParseCandidate:
    candidate_id: str
    facts: list[str]
    system_type_candidates: list[SystemTypeCandidate]
    score: float
    warnings: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("parse candidate score must be between 0 and 1")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ParseCandidate":
        values = dict(data)
        values["facts"] = list(values.get("facts") or [])
        values["system_type_candidates"] = [
            SystemTypeCandidate.from_dict(item)
            for item in values.get("system_type_candidates") or []
        ]
        values["warnings"] = list(values.get("warnings") or [])
        values["missing_info"] = list(values.get("missing_info") or [])
        values["conflicts"] = list(values.get("conflicts") or [])
        return cls(**values)


@dataclass
class CanonicalProblemV2:
    schema_version: str
    raw_text: str
    normalized_text: str
    language: str
    system_type: str
    subtype: str | None
    facts: list[ExtractedFact]
    assumptions: list[AssumptionRecord]
    parse_candidates: list[ParseCandidate]
    requested_outputs: list[str]
    flags: dict[str, bool]
    objects: list[dict[str, Any]]
    missing_info: list[str]
    conflicts: list[str]
    warnings: list[str]
    legacy_view: dict[str, Any]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != "2.0":
            raise ValueError("CanonicalProblemV2 schema_version must be '2.0'")
        if not self.fingerprint:
            self.refresh_fingerprint()

    def canonical_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "system_type": self.system_type,
            "subtype": self.subtype,
            "facts": [asdict(item) for item in self.facts],
            "assumptions": [asdict(item) for item in self.assumptions],
            "parse_candidates": [asdict(item) for item in self.parse_candidates],
            "requested_outputs": self.requested_outputs,
            "flags": self.flags,
            "objects": self.objects,
            "missing_info": self.missing_info,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "legacy_view": self.legacy_view,
        }
        return _canonicalize(payload)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def compute_fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def refresh_fingerprint(self) -> str:
        self.fingerprint = self.compute_fingerprint()
        return self.fingerprint

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source"] = "rule_based_extractor"
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalProblemV2":
        values = dict(data)
        values.pop("source", None)
        supplied_fingerprint = str(values.pop("fingerprint", "") or "")
        values["facts"] = [ExtractedFact.from_dict(item) for item in values.get("facts") or []]
        values["assumptions"] = [
            AssumptionRecord.from_dict(item) for item in values.get("assumptions") or []
        ]
        values["parse_candidates"] = [
            ParseCandidate.from_dict(item) for item in values.get("parse_candidates") or []
        ]
        values["requested_outputs"] = list(values.get("requested_outputs") or [])
        values["flags"] = dict(values.get("flags") or {})
        values["objects"] = [dict(item) for item in values.get("objects") or []]
        values["missing_info"] = list(values.get("missing_info") or [])
        values["conflicts"] = list(values.get("conflicts") or [])
        values["warnings"] = list(values.get("warnings") or [])
        values["legacy_view"] = dict(values.get("legacy_view") or {})
        obj = cls(**values, fingerprint="")
        computed = obj.compute_fingerprint()
        if supplied_fingerprint and supplied_fingerprint != computed:
            raise ValueError("CanonicalProblemV2 fingerprint does not match serialized content")
        obj.fingerprint = supplied_fingerprint or computed
        return obj

    @classmethod
    def from_json(cls, payload: str) -> "CanonicalProblemV2":
        return cls.from_dict(json.loads(payload))
