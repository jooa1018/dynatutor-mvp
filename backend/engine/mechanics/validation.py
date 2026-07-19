from __future__ import annotations

"""Fail-closed validation for the generic mechanics draft graph.

This module deliberately validates only the typed draft graph and its supplied
evidence.  It does not infer mechanics from problem text, normalize units, or
select a solver route.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
import math

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.errors import (
    MechanicsIssueCode,
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.math_ast import (
    AstValidationIssue,
    SymbolDefinition,
    validate_math_expressions,
)
from engine.textbook_parser.evidence_alignment import (
    _normalized_number,
    _normalized_unit,
    quantity_occurrences,
)


_MAX_PROBLEM_TEXT_LENGTH = 200_000
_MAX_REFERENCE_ITEMS = 1_024
_MAX_APPROVED_ASSUMPTIONS = 128
_MAX_AUTHORIZATIONS = 512
_MAX_QUOTE_OCCURRENCES = 1_000
_MAX_TOTAL_QUOTE_SCAN = 20_000_000
_MAX_IDENTIFIER_LENGTH = 64
_MAX_EVIDENCE_QUOTE_LENGTH = 1_000
_MAX_RAW_VALUE_LENGTH = 80
_MAX_RAW_UNIT_LENGTH = 48
_MAX_RECOGNIZED_LABEL_LENGTH = 200

_COLLECTION_SPECS = (
    ("source_assets", "asset_id", 32, "asset"),
    ("source_evidence", "evidence_id", 512, "evidence"),
    ("entities", "entity_id", 128, "entity"),
    ("points", "point_id", 256, "point"),
    ("reference_frames", "frame_id", 64, "frame"),
    ("motion_intervals", "interval_id", 64, "interval"),
    ("events", "event_id", 128, "event"),
    ("symbols", "symbol_id", 512, "symbol"),
    ("quantities", "quantity_id", 512, "quantity"),
    ("geometry", "relation_id", 256, "geometry"),
    ("interactions", "interaction_id", 256, "interaction"),
    ("constraints", "constraint_id", 512, "constraint"),
    ("state_conditions", "state_condition_id", 256, "state"),
    ("queries", "query_id", 64, "query"),
    ("principle_hints", "hint_id", 64, "hint"),
    ("assumptions", "assumption_id", 64, "assumption"),
    ("ambiguities", "ambiguity_id", 64, "ambiguity"),
    ("unsupported_features", "feature_code", 64, "unsupported"),
)

_AST_CODES = {
    "unsupported": MechanicsIssueCode.ast_unsupported,
    "resource_limit": MechanicsIssueCode.ast_resource_limit,
    "symbol_missing": MechanicsIssueCode.ast_symbol_missing,
    "dimension_mismatch": MechanicsIssueCode.ast_dimension_mismatch,
    "shape_mismatch": MechanicsIssueCode.ast_shape_mismatch,
}


class ValidationTerminal(str, Enum):
    accepted = "accepted"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    unsupported = "unsupported"
    invalid = "invalid"


@dataclass(frozen=True)
class CorrectionAuthorization:
    correction_id: str
    subject_id: str
    role: str
    raw_value: str
    raw_unit: str
    interval_id: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class AssumptionAuthorization:
    assumption_id: str
    subject_id: str
    role: str
    raw_value: str
    raw_unit: str
    interval_id: str | None = None


@dataclass(frozen=True)
class DraftValidationResult:
    terminal: ValidationTerminal
    issues: tuple[MechanicsValidationIssue, ...]

    @property
    def accepted(self) -> bool:
        return self.terminal is ValidationTerminal.accepted

    @property
    def blocked(self) -> bool:
        return not self.accepted


@dataclass(frozen=True)
class _TextEvidenceFacts:
    quantity_text: str | None
    quantity_start: int | None
    tokens: tuple[_NumericToken, ...]


@dataclass(frozen=True)
class _FigureEvidenceFacts:
    tokens: tuple[_NumericToken, ...]
    identity_prefix: tuple[object, ...] | None


@dataclass(frozen=True)
class _NumericToken:
    value: str
    unit: str
    start: int
    number_end: int
    end: int


@dataclass(frozen=True)
class _NumericBinding:
    identities: tuple[tuple[object, ...], ...]
    unconfirmed_figure: bool = False


def _enum_value(value: object) -> str | None:
    raw_value = getattr(value, "value", value)
    return raw_value if type(raw_value) is str else None


def _bounded_string(
    value: object,
    *,
    maximum: int,
    allow_empty: bool = False,
) -> bool:
    """Check contract string bounds before hashing or normalization."""

    return (
        type(value) is str
        and len(value) <= maximum
        and (allow_empty or bool(value.strip()))
    )


def _bounded_identifier(value: object) -> bool:
    return _bounded_string(value, maximum=_MAX_IDENTIFIER_LENGTH)


def _add_issue(
    issues: list[MechanicsValidationIssue],
    code: MechanicsIssueCode,
    message: str,
    path: str,
    *,
    severity: MechanicsIssueSeverity = MechanicsIssueSeverity.error,
    referenced_id: str | None = None,
) -> None:
    issues.append(
        MechanicsValidationIssue(
            code=code,
            severity=severity,
            message=message,
            path=path,
            referenced_id=referenced_id,
        )
    )


def _snapshot(
    value: object,
    *,
    limit: int,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> tuple[object, ...]:
    """Copy a collection with an explicit upper bound and fail closed on abuse."""

    if isinstance(value, (str, bytes, bytearray, Mapping)):
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "collection must be a bounded non-mapping iterable",
            path,
        )
        return ()
    try:
        iterator = iter(value)  # type: ignore[arg-type]
    except Exception:
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "collection could not be iterated safely",
            path,
        )
        return ()

    items: list[object] = []
    for index in range(limit + 1):
        try:
            item = next(iterator)
        except StopIteration:
            return tuple(items)
        except Exception:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "collection iteration failed",
                path,
            )
            return tuple(items)
        if index >= limit:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                f"collection exceeds its bound of {limit}",
                path,
            )
            return tuple(items)
        items.append(item)
    return tuple(items)


def _index_namespace(
    items: tuple[object, ...],
    *,
    id_attribute: str,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> dict[str, object]:
    index: dict[str, object] = {}
    for item_index, item in enumerate(items):
        identifier = getattr(item, id_attribute, None)
        item_path = f"{path}.{item_index}.{id_attribute}"
        if not _bounded_identifier(identifier):
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "namespace item identifier is not an exact bounded string",
                item_path,
            )
            continue
        if identifier in index:
            _add_issue(
                issues,
                MechanicsIssueCode.duplicate_id,
                "identifier is duplicated within its namespace",
                item_path,
                referenced_id=identifier,
            )
            continue
        index[identifier] = item
    return index


def _index_global_namespaces(
    collections: Mapping[str, tuple[object, ...]],
    *,
    issues: list[MechanicsValidationIssue],
) -> dict[str, object]:
    """Require one ID namespace for every typed and bare graph reference."""

    global_index: dict[str, object] = {}
    owners: dict[str, str] = {}
    for attribute, id_attribute, _, namespace in _COLLECTION_SPECS:
        for item_index, item in enumerate(collections.get(attribute, ())):
            identifier = getattr(item, id_attribute, None)
            if not _bounded_identifier(identifier):
                continue
            previous_namespace = owners.get(identifier)
            if previous_namespace is not None:
                if previous_namespace != namespace:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.duplicate_id,
                        "identifier collides across graph namespaces",
                        f"{attribute}.{item_index}.{id_attribute}",
                        referenced_id=identifier,
                    )
                continue
            owners[identifier] = namespace
            global_index[identifier] = item
    return global_index


def _reference(
    value: object,
    targets: Mapping[str, object] | set[str],
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
    code: MechanicsIssueCode = MechanicsIssueCode.invalid_reference,
    message: str = "reference does not resolve in the draft graph",
) -> bool:
    if not _bounded_identifier(value) or value not in targets:
        _add_issue(
            issues,
            code,
            message,
            path,
            referenced_id=value if _bounded_identifier(value) else None,
        )
        return False
    return True


def _optional_reference(
    value: object,
    targets: Mapping[str, object] | set[str],
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
    code: MechanicsIssueCode = MechanicsIssueCode.invalid_reference,
    message: str = "reference does not resolve in the draft graph",
) -> bool:
    if value is None:
        return True
    return _reference(
        value,
        targets,
        path=path,
        issues=issues,
        code=code,
        message=message,
    )


def _references(
    item: object,
    attribute: str,
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> tuple[object, ...]:
    return _snapshot(
        getattr(item, attribute, None),
        limit=_MAX_REFERENCE_ITEMS,
        path=f"{path}.{attribute}",
        issues=issues,
    )


def _validate_reference_list(
    item: object,
    attribute: str,
    targets: Mapping[str, object] | set[str],
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> tuple[object, ...]:
    values = _references(item, attribute, path=path, issues=issues)
    for index, value in enumerate(values):
        _reference(
            value,
            targets,
            path=f"{path}.{attribute}.{index}",
            issues=issues,
        )
    return values


def _span_values(span: object) -> tuple[int, int] | None:
    start = getattr(span, "start", None)
    end = getattr(span, "end", None)
    if type(start) is not int or type(end) is not int:
        return None
    return start, end


def _quote_positions(
    text: str,
    quote: str,
    *,
    cache: dict[str, tuple[int, ...]],
    remaining_scan_budget: list[int],
) -> tuple[int, ...] | None:
    """Bound exact, overlap-aware quote lookup with a per-draft cache."""

    cached = cache.get(quote)
    if cached is not None:
        return cached
    if len(text) > remaining_scan_budget[0]:
        return None
    remaining_scan_budget[0] -= len(text)
    positions: list[int] = []
    cursor = 0
    for _ in range(_MAX_QUOTE_OCCURRENCES):
        found = text.find(quote, cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
    result = tuple(positions)
    cache[quote] = result
    return result


def _validate_text_evidence(
    problem_text: object,
    evidence_items: tuple[object, ...],
    *,
    issues: list[MechanicsValidationIssue],
) -> dict[str, _TextEvidenceFacts]:
    facts: dict[str, _TextEvidenceFacts] = {}
    text_is_usable = type(problem_text) is str
    if not text_is_usable:
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "problem_text must be a string",
            "problem_text",
        )
    elif len(problem_text) > _MAX_PROBLEM_TEXT_LENGTH:
        text_is_usable = False
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "problem_text exceeds the validation bound",
            "problem_text",
        )

    quote_cache: dict[str, tuple[int, ...]] = {}
    remaining_scan_budget = [_MAX_TOTAL_QUOTE_SCAN]
    seen_numeric_tokens: dict[tuple[object, ...], str] = {}
    for index, evidence in enumerate(evidence_items):
        if _enum_value(getattr(evidence, "kind", None)) != "text":
            continue
        path = f"source_evidence.{index}"
        evidence_id = getattr(evidence, "evidence_id", None)
        quote = getattr(evidence, "quote", None)
        occurrence_index = getattr(evidence, "occurrence_index", None)
        source_values = _span_values(getattr(evidence, "source_span", None))
        source_is_valid = False

        quote_is_usable = _bounded_string(
            quote,
            maximum=_MAX_EVIDENCE_QUOTE_LENGTH,
        )
        if not quote_is_usable:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "text evidence quote must be an exact non-empty string of at most 1000 characters",
                f"{path}.quote",
            )
        if (
            type(occurrence_index) is not int
            or occurrence_index < 0
            or occurrence_index >= _MAX_QUOTE_OCCURRENCES
        ):
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "text evidence occurrence_index must be in the contract range 0..999",
                f"{path}.occurrence_index",
            )
        if source_values is None:
            _add_issue(
                issues,
                MechanicsIssueCode.evidence_span_mismatch,
                "text evidence source span is malformed",
                f"{path}.source_span",
            )
        elif text_is_usable:
            source_start, source_end = source_values
            if not (0 <= source_start < source_end <= len(problem_text)):
                _add_issue(
                    issues,
                    MechanicsIssueCode.evidence_span_mismatch,
                    "text evidence source span is outside problem_text",
                    f"{path}.source_span",
                )
            elif quote_is_usable and problem_text[source_start:source_end] != quote:
                _add_issue(
                    issues,
                    MechanicsIssueCode.evidence_span_mismatch,
                    "text evidence quote does not exactly match its source span",
                    f"{path}.source_span",
                )
            else:
                source_is_valid = quote_is_usable

        if text_is_usable and quote_is_usable:
            positions = _quote_positions(
                problem_text,
                quote,
                cache=quote_cache,
                remaining_scan_budget=remaining_scan_budget,
            )
            if positions is None:
                _add_issue(
                    issues,
                    MechanicsIssueCode.schema_error,
                    "text evidence quote scan budget was exhausted",
                    f"{path}.quote",
                )
            elif not positions:
                _add_issue(
                    issues,
                    MechanicsIssueCode.evidence_quote_missing,
                    "text evidence quote does not occur in problem_text",
                    f"{path}.quote",
                )
            elif (
                type(occurrence_index) is int
                and 0 <= occurrence_index < _MAX_QUOTE_OCCURRENCES
            ):
                expected_start = (
                    positions[occurrence_index]
                    if occurrence_index < len(positions)
                    else None
                )
                if source_values is None or expected_start != source_values[0]:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.evidence_occurrence_mismatch,
                        "text evidence occurrence_index does not identify its source span",
                        f"{path}.occurrence_index",
                    )

        quantity_text: str | None = None
        quantity_start: int | None = None
        numeric_tokens: tuple[_NumericToken, ...] = ()
        quantity_span = getattr(evidence, "quantity_span", None)
        if quantity_span is not None:
            quantity_values = _span_values(quantity_span)
            if quantity_values is None or source_values is None or not text_is_usable:
                _add_issue(
                    issues,
                    MechanicsIssueCode.quantity_span_mismatch,
                    "quantity_span is malformed or cannot be checked",
                    f"{path}.quantity_span",
                )
            else:
                quantity_start, quantity_end = quantity_values
                source_start, source_end = source_values
                if not (
                    0 <= quantity_start < quantity_end <= len(problem_text)
                    and source_start <= quantity_start < quantity_end <= source_end
                ):
                    _add_issue(
                        issues,
                        MechanicsIssueCode.quantity_span_mismatch,
                        "quantity_span must be absolute and contained by source_span",
                        f"{path}.quantity_span",
                    )
                elif source_is_valid:
                    quantity_text = problem_text[quantity_start:quantity_end]
                    quantity_start = quantity_values[0]
                    numeric_tokens = _token_pairs(
                        quantity_text,
                        max_length=_MAX_EVIDENCE_QUOTE_LENGTH,
                    )
                else:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.quantity_span_mismatch,
                        "quantity_span cannot be trusted when its source quote is invalid",
                        f"{path}.quantity_span",
                    )

        if _bounded_identifier(evidence_id) and quantity_start is not None:
            for token in numeric_tokens:
                identity = (
                    "text",
                    quantity_start + token.start,
                    quantity_start + token.number_end,
                )
                previous = seen_numeric_tokens.get(identity)
                if previous is not None and previous != evidence_id:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.quantity_occurrence_reused,
                        "the same physical text numeric token is exposed by multiple evidence records",
                        f"{path}.quantity_span",
                        referenced_id=previous,
                    )
                else:
                    seen_numeric_tokens[identity] = evidence_id

        if _bounded_identifier(evidence_id) and evidence_id not in facts:
            facts[evidence_id] = _TextEvidenceFacts(
                quantity_text=quantity_text,
                quantity_start=quantity_start,
                tokens=numeric_tokens,
            )
    return facts


def _validate_asset_page_topology(
    asset: object,
    assets: Mapping[str, object],
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> None:
    page_id = getattr(asset, "page_id", None)
    if page_id is None:
        return
    if not _reference(
        page_id,
        assets,
        path=f"{path}.page_id",
        issues=issues,
        code=MechanicsIssueCode.figure_page_mismatch,
        message="source asset page_id does not resolve",
    ):
        return
    page_asset = assets[page_id]
    if _enum_value(getattr(page_asset, "kind", None)) != "page":
        _add_issue(
            issues,
            MechanicsIssueCode.figure_page_mismatch,
            "source asset page_id must identify a page asset",
            f"{path}.page_id",
            referenced_id=page_id,
        )
        return
    asset_id = getattr(asset, "asset_id", None)
    asset_kind = _enum_value(getattr(asset, "kind", None))
    if asset_kind == "page" and asset_id != page_id:
        _add_issue(
            issues,
            MechanicsIssueCode.figure_page_mismatch,
            "a page asset page_id must equal its asset_id",
            f"{path}.page_id",
            referenced_id=page_id,
        )
        return
    if asset_id == page_id:
        return
    asset_parent = getattr(asset, "parent_asset_id", None)
    topology_matches = (
        asset_kind == "image"
        and (getattr(asset, "page_id", None) == page_id or asset_parent == page_id)
    )
    if not topology_matches:
        _add_issue(
            issues,
            MechanicsIssueCode.figure_page_mismatch,
            "source asset parent topology conflicts with its page asset",
            f"{path}.parent_asset_id",
            referenced_id=page_id,
        )


def _validate_figure_evidence(
    evidence_items: tuple[object, ...],
    assets: Mapping[str, object],
    *,
    issues: list[MechanicsValidationIssue],
) -> dict[str, _FigureEvidenceFacts]:
    facts: dict[str, _FigureEvidenceFacts] = {}
    seen_numeric_tokens: dict[tuple[object, ...], str] = {}
    for index, evidence in enumerate(evidence_items):
        if _enum_value(getattr(evidence, "kind", None)) != "figure":
            continue
        path = f"source_evidence.{index}"
        asset_id = getattr(evidence, "asset_id", None)
        if not _reference(
            asset_id,
            assets,
            path=f"{path}.asset_id",
            issues=issues,
            code=MechanicsIssueCode.figure_asset_missing,
            message="figure evidence asset_id does not resolve",
        ):
            continue
        asset = assets[asset_id]
        asset_kind = _enum_value(getattr(asset, "kind", None))
        if asset_kind not in {"image", "page"}:
            _add_issue(
                issues,
                MechanicsIssueCode.figure_asset_invalid,
                "numeric figure evidence requires an image or page source asset",
                f"{path}.asset_id",
                referenced_id=asset_id,
            )
            continue

        topology_is_valid = True
        page_scope: str | None = asset_id if asset_kind == "page" else None
        page_id = getattr(evidence, "page_id", None)
        if page_id is not None:
            if not _reference(
                page_id,
                assets,
                path=f"{path}.page_id",
                issues=issues,
                code=MechanicsIssueCode.figure_page_mismatch,
                message="figure evidence page_id does not resolve to a source asset",
            ):
                topology_is_valid = False
                continue
            page_asset = assets[page_id]
            if _enum_value(getattr(page_asset, "kind", None)) != "page":
                _add_issue(
                    issues,
                    MechanicsIssueCode.figure_page_mismatch,
                    "figure evidence page_id must identify a page asset",
                    f"{path}.page_id",
                    referenced_id=page_id,
                )
                topology_is_valid = False
                continue
            asset_page_id = getattr(asset, "page_id", None)
            asset_parent_id = getattr(asset, "parent_asset_id", None)
            topology_matches = (
                (asset_kind == "page" and asset_id == page_id)
                or (
                    asset_kind == "image"
                    and (asset_page_id == page_id or asset_parent_id == page_id)
                )
            )
            if (
                (asset_page_id is not None and asset_page_id != page_id)
                or (asset_kind == "page" and asset_id != page_id)
                or not topology_matches
            ):
                _add_issue(
                    issues,
                    MechanicsIssueCode.figure_page_mismatch,
                    "figure evidence page_id conflicts with the referenced asset",
                    f"{path}.page_id",
                    referenced_id=page_id,
                )
                topology_is_valid = False
            else:
                page_scope = page_id
        elif asset_kind == "image":
            asset_page_id = getattr(asset, "page_id", None)
            asset_parent_id = getattr(asset, "parent_asset_id", None)
            for candidate in (asset_page_id, asset_parent_id):
                candidate_asset = assets.get(candidate) if _bounded_identifier(candidate) else None
                if _enum_value(getattr(candidate_asset, "kind", None)) == "page":
                    page_scope = candidate
                    break

        region = getattr(evidence, "region", None)
        region_key = _figure_region_key(region)
        if region_key is None:
            _add_issue(
                issues,
                MechanicsIssueCode.figure_region_invalid,
                "figure evidence region is missing or malformed",
                f"{path}.region",
            )

        label = getattr(evidence, "recognized_label", None)
        label_is_usable = label is None or _bounded_string(
            label,
            maximum=_MAX_RECOGNIZED_LABEL_LENGTH,
        )
        if not label_is_usable:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "recognized_label must be an exact non-empty string of at most 200 characters",
                f"{path}.recognized_label",
            )
        tokens = (
            _token_pairs(label, max_length=_MAX_RECOGNIZED_LABEL_LENGTH)
            if label_is_usable and label is not None
            else ()
        )
        identity_prefix = (
            ("figure", asset_id, page_scope, region_key)
            if topology_is_valid
            and _bounded_identifier(page_scope)
            and region_key is not None
            else None
        )
        evidence_id = getattr(evidence, "evidence_id", None)
        if _bounded_identifier(evidence_id) and identity_prefix is not None:
            for token in tokens:
                identity = (*identity_prefix, token.start, token.number_end)
                previous = seen_numeric_tokens.get(identity)
                if previous is not None and previous != evidence_id:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.quantity_occurrence_reused,
                        "the same physical figure numeric token is exposed by multiple evidence records",
                        f"{path}.recognized_label",
                        referenced_id=previous,
                    )
                else:
                    seen_numeric_tokens[identity] = evidence_id
        if _bounded_identifier(evidence_id) and evidence_id not in facts:
            facts[evidence_id] = _FigureEvidenceFacts(
                tokens=tokens,
                identity_prefix=identity_prefix,
            )
    return facts


def _figure_region_key(region: object) -> tuple[object, ...] | None:
    """Return a bounded, hashable canonical region identity for reuse checks."""

    bbox = getattr(region, "bbox", None)
    if bbox is not None:
        values = tuple(
            getattr(bbox, field, None)
            for field in ("left", "top", "right", "bottom")
        )
        if (
            all(type(value) in {int, float} and math.isfinite(value) for value in values)
            and 0.0 <= values[0] < values[2] <= 1.0
            and 0.0 <= values[1] < values[3] <= 1.0
        ):
            return ("bbox", *(float(value) for value in values))
        return None
    polygon = getattr(region, "polygon", None)
    if isinstance(polygon, (list, tuple)) and 3 <= len(polygon) <= 32:
        points: list[tuple[object, object]] = []
        for point in polygon:
            x = getattr(point, "x", None)
            y = getattr(point, "y", None)
            if (
                type(x) not in {int, float}
                or type(y) not in {int, float}
                or not math.isfinite(x)
                or not math.isfinite(y)
                or not 0.0 <= x <= 1.0
                or not 0.0 <= y <= 1.0
            ):
                return None
            points.append((float(x), float(y)))
        return ("polygon", tuple(points))
    return None


def _validate_direction(
    direction: object,
    *,
    path: str,
    frames: Mapping[str, object],
    symbols: Mapping[str, object],
    issues: list[MechanicsValidationIssue],
) -> None:
    if direction is None:
        return
    kind = _enum_value(getattr(direction, "kind", None))
    if kind in {"axis", "vector"}:
        _reference(
            getattr(direction, "frame_id", None),
            frames,
            path=f"{path}.frame_id",
            issues=issues,
        )
    elif kind == "symbol":
        _reference(
            getattr(direction, "symbol_id", None),
            symbols,
            path=f"{path}.symbol_id",
            issues=issues,
        )
        _optional_reference(
            getattr(direction, "frame_id", None),
            frames,
            path=f"{path}.frame_id",
            issues=issues,
        )
    elif kind != "semantic":
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "direction binding kind is not recognized",
            path,
        )


def _validate_frame_origin(
    origin: object,
    *,
    path: str,
    entities: Mapping[str, object],
    points: Mapping[str, object],
    frames: Mapping[str, object],
    issues: list[MechanicsValidationIssue],
) -> None:
    kind = _enum_value(getattr(origin, "kind", None))
    if kind == "world":
        return
    if kind == "point":
        _reference(getattr(origin, "point_id", None), points, path=f"{path}.point_id", issues=issues)
    elif kind == "entity":
        _reference(getattr(origin, "entity_id", None), entities, path=f"{path}.entity_id", issues=issues)
    elif kind == "frame":
        _reference(getattr(origin, "frame_id", None), frames, path=f"{path}.frame_id", issues=issues)
    else:
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "reference frame origin kind is not recognized",
            path,
        )


def _approved_ids(
    approved_assumption_ids: Collection[str],
    *,
    issues: list[MechanicsValidationIssue],
) -> set[str]:
    values = _snapshot(
        approved_assumption_ids,
        limit=_MAX_APPROVED_ASSUMPTIONS,
        path="approved_assumption_ids",
        issues=issues,
    )
    approved: set[str] = set()
    for index, value in enumerate(values):
        if not _bounded_identifier(value):
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "approved_assumption_ids must contain exact bounded identifier strings",
                f"approved_assumption_ids.{index}",
            )
            continue
        approved.add(value)
    return approved


def _trusted_authorization_map(
    value: Mapping[str, object],
    authorization_type: type[object],
    identifier_attribute: str,
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "trusted authorizations must be a bounded mapping",
            path,
        )
        return {}
    trusted: dict[str, object] = {}
    try:
        iterator = iter(value.items())
    except Exception:
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "trusted authorization mapping could not be iterated safely",
            path,
        )
        return trusted
    for index in range(_MAX_AUTHORIZATIONS + 1):
        try:
            key, authorization = next(iterator)
        except StopIteration:
            break
        except Exception:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "trusted authorization mapping iteration failed",
                path,
            )
            break
        if index >= _MAX_AUTHORIZATIONS:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "trusted authorization mapping exceeds its bound",
                path,
            )
            break
        item_path = f"{path}.{index}"
        authorization_is_exact = type(authorization) is authorization_type
        if (
            not _bounded_identifier(key)
            or not authorization_is_exact
            or getattr(authorization, identifier_attribute, None) != key
        ):
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "trusted authorization key and immutable authorization must agree",
                item_path,
                referenced_id=key if _bounded_identifier(key) else None,
            )
            continue

        string_specs = (
            (identifier_attribute, _MAX_IDENTIFIER_LENGTH, False),
            ("subject_id", _MAX_IDENTIFIER_LENGTH, False),
            ("role", _MAX_IDENTIFIER_LENGTH, False),
            ("raw_value", _MAX_RAW_VALUE_LENGTH, False),
            ("raw_unit", _MAX_RAW_UNIT_LENGTH, True),
            ("interval_id", _MAX_IDENTIFIER_LENGTH, False),
        )
        if authorization_type is CorrectionAuthorization:
            string_specs = (*string_specs, ("event_id", _MAX_IDENTIFIER_LENGTH, False))
        fields_are_valid = True
        for field, maximum, allow_empty in string_specs:
            field_value = getattr(authorization, field, None)
            if field in {"interval_id", "event_id"} and field_value is None:
                continue
            if not _bounded_string(
                field_value,
                maximum=maximum,
                allow_empty=allow_empty,
            ):
                fields_are_valid = False
                _add_issue(
                    issues,
                    MechanicsIssueCode.schema_error,
                    "trusted authorization contains an invalid or oversized string",
                    f"{item_path}.{field}",
                    referenced_id=key,
                )
        if not fields_are_valid:
            continue
        trusted[key] = authorization
    return trusted


def _trusted_ids(
    value: Collection[str],
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> set[str]:
    values = _snapshot(value, limit=_MAX_AUTHORIZATIONS, path=path, issues=issues)
    result: set[str] = set()
    for index, item in enumerate(values):
        if not _bounded_identifier(item):
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "trusted evidence identifiers must be exact bounded strings",
                f"{path}.{index}",
            )
            continue
        result.add(item)
    return result


def _raw_pair_is_bounded(raw_value: object, raw_unit: object) -> bool:
    return _bounded_string(
        raw_value,
        maximum=_MAX_RAW_VALUE_LENGTH,
    ) and _bounded_string(
        raw_unit,
        maximum=_MAX_RAW_UNIT_LENGTH,
        allow_empty=True,
    )


def _canonical_unit(raw_unit: object) -> str | None:
    if not _bounded_string(
        raw_unit,
        maximum=_MAX_RAW_UNIT_LENGTH,
        allow_empty=True,
    ):
        return None
    unit_text = raw_unit.strip()
    if not unit_text:
        return ""
    probe = f"0 {unit_text}"
    try:
        tokens = quantity_occurrences(probe)
    except Exception:
        return None
    if (
        len(tokens) != 1
        or tokens[0].start != 0
        or tokens[0].end != len(probe)
        or tokens[0].raw_value != "0"
        or tokens[0].raw_unit != unit_text
    ):
        return None
    try:
        return _normalized_unit(tokens[0].raw_unit)
    except Exception:
        return None


def _canonical_pair(raw_value: object, raw_unit: object) -> tuple[str, str] | None:
    """Accept only one complete scalar number and one adjacent complete unit."""

    if not _raw_pair_is_bounded(raw_value, raw_unit):
        return None
    value_text = raw_value.strip()
    unit_text = raw_unit.strip()
    try:
        value_tokens = quantity_occurrences(value_text)
    except Exception:
        return None
    if (
        len(value_tokens) != 1
        or value_tokens[0].start != 0
        or value_tokens[0].end != len(value_text)
        or value_tokens[0].raw_value != value_text
        or value_tokens[0].raw_unit != ""
    ):
        return None

    pair_text = value_text if not unit_text else f"{value_text} {unit_text}"
    try:
        pair_tokens = quantity_occurrences(pair_text)
    except Exception:
        return None
    if (
        len(pair_tokens) != 1
        or pair_tokens[0].start != 0
        or pair_tokens[0].end != len(pair_text)
        or pair_tokens[0].raw_value != value_text
        or pair_tokens[0].raw_unit != unit_text
    ):
        return None
    try:
        return (
            _normalized_number(pair_tokens[0].raw_value),
            _normalized_unit(pair_tokens[0].raw_unit),
        )
    except Exception:
        return None


def _token_pairs(
    text: object,
    *,
    max_length: int,
) -> tuple[_NumericToken, ...]:
    if not _bounded_string(text, maximum=max_length):
        return ()
    try:
        parsed = quantity_occurrences(text)
    except Exception:
        return ()
    pairs: list[_NumericToken] = []
    for token in parsed:
        try:
            value = _normalized_number(token.raw_value)
            unit = _normalized_unit(token.raw_unit)
        except Exception:
            continue
        pairs.append(
            _NumericToken(
                value=value,
                unit=unit,
                start=token.start,
                number_end=token.start + len(token.raw_value),
                end=token.end,
            )
        )
    return tuple(pairs)


def _expected_numeric_pairs(
    quantity: object,
    raw_value: str,
    raw_unit: str,
) -> tuple[tuple[tuple[str, str], ...], bool]:
    """Build canonical pairs without evaluating the model-supplied raw text."""

    shape = _enum_value(getattr(quantity, "shape", None))
    if shape == "scalar":
        canonical = _canonical_pair(raw_value, raw_unit)
        return ((canonical,) if canonical is not None else ()), canonical is None
    if shape != "vector" or not _bounded_string(
        raw_value,
        maximum=_MAX_RAW_VALUE_LENGTH,
    ):
        return (), True
    # ``quantity_occurrences`` deliberately accepts localized scalar number
    # spellings, including some comma forms.  A vector needs a smaller,
    # unambiguous grammar: two or three complete scalar components separated by
    # literal commas, with only horizontal whitespace around each component.
    # Canonicalize each scalar through the existing fail-closed scalar path so
    # model text is never evaluated and a component cannot smuggle its own unit.
    if any(
        character.isspace() and character not in {" ", "\t"}
        for character in raw_value
    ):
        return (), True
    value_text = raw_value.strip(" \t")
    component_texts = value_text.split(",")
    if len(component_texts) not in {2, 3}:
        return (), True
    expected: list[tuple[str, str]] = []
    for component_text in component_texts:
        component = component_text.strip(" \t")
        if not component:
            return (), True
        canonical = _canonical_pair(component, raw_unit)
        if canonical is None:
            return (), True
        expected.append(canonical)
    return tuple(expected), False


def _pairs_present(
    expected: tuple[tuple[str, str], ...],
    tokens: tuple[_NumericToken, ...],
) -> bool:
    remaining = [(token.value, token.unit) for token in tokens]
    for pair in expected:
        try:
            position = remaining.index(pair)
        except ValueError:
            return False
        remaining.pop(position)
    return True


def _evidence_presence(
    expected: tuple[tuple[str, str], ...],
    tokens: tuple[_NumericToken, ...],
) -> tuple[bool, bool]:
    token_values = {token.value for token in tokens}
    token_units = {token.unit for token in tokens}
    return (
        bool(expected) and all(value in token_values for value, _ in expected),
        bool(expected) and all(unit in token_units for _, unit in expected),
    )


def _binding_from_tokens(
    expected: tuple[tuple[str, str], ...],
    tokens: tuple[_NumericToken, ...],
    *,
    identity_prefix: tuple[object, ...],
    absolute_offset: int,
    unconfirmed_figure: bool = False,
) -> tuple[_NumericBinding | None, bool]:
    """Bind one scalar token or an exact vector/tensor component sequence."""

    if len(expected) == 1:
        matching = [
            token for token in tokens if (token.value, token.unit) == expected[0]
        ]
        if len(matching) != 1:
            return None, len(matching) > 1
        token = matching[0]
        return (
            _NumericBinding(
                identities=(
                    (
                        *identity_prefix,
                        absolute_offset + token.start,
                        absolute_offset + token.number_end,
                    ),
                ),
                unconfirmed_figure=unconfirmed_figure,
            ),
            False,
        )
    if len(expected) > 1 and len(tokens) == len(expected):
        if tuple((token.value, token.unit) for token in tokens) == expected:
            identities = tuple(
                (
                    *identity_prefix,
                    absolute_offset + token.start,
                    absolute_offset + token.number_end,
                )
                for token in tokens
            )
            return _NumericBinding(identities, unconfirmed_figure), False
    return None, len(expected) > 1 and _pairs_present(expected, tokens)


def _claim_numeric_binding(
    binding: _NumericBinding,
    quantity_id: object,
    *,
    path: str,
    used_occurrences: dict[tuple[object, ...], str],
    issues: list[MechanicsValidationIssue],
) -> None:
    if not _bounded_identifier(quantity_id):
        return
    claimed_here: set[tuple[object, ...]] = set()
    for identity in binding.identities:
        if identity in claimed_here:
            _add_issue(
                issues,
                MechanicsIssueCode.quantity_occurrence_reused,
                "one numeric evidence token cannot satisfy repeated vector/tensor components",
                path,
                referenced_id=quantity_id,
            )
            continue
        claimed_here.add(identity)
        previous = used_occurrences.get(identity)
        if previous is not None and previous != quantity_id:
            _add_issue(
                issues,
                MechanicsIssueCode.quantity_occurrence_reused,
                "one source numeric token cannot ground multiple explicit quantities",
                path,
                referenced_id=previous,
            )
            continue
        used_occurrences[identity] = quantity_id


def _authorization_matches(
    quantity: object,
    authorization: object,
    *,
    raw_value: str,
    raw_unit: str,
    correction: bool,
) -> bool:
    if correction:
        if type(authorization) is not CorrectionAuthorization:
            return False
        event_matches = authorization.event_id == getattr(quantity, "event_id", None)
    else:
        if type(authorization) is not AssumptionAuthorization:
            return False
        event_matches = getattr(quantity, "event_id", None) is None
    return (
        authorization.subject_id == getattr(quantity, "subject_id", None)
        and _enum_value(authorization.role) == _enum_value(getattr(quantity, "role", None))
        and authorization.raw_value == raw_value
        and authorization.raw_unit == raw_unit
        and authorization.interval_id == getattr(quantity, "interval_id", None)
        and event_matches
    )


def _validate_symbol_quantity_bindings(
    symbol_items: tuple[object, ...],
    quantity_items: tuple[object, ...],
    symbols: Mapping[str, object],
    quantities: Mapping[str, object],
    *,
    issues: list[MechanicsValidationIssue],
) -> None:
    """Enforce reciprocal, one-to-one typed symbol bindings before AST checks."""

    claimed_quantities: dict[str, str] = {}
    for index, symbol in enumerate(symbol_items):
        path = f"symbols.{index}"
        symbol_id = getattr(symbol, "symbol_id", None)
        quantity_id = getattr(symbol, "quantity_id", None)
        if not _bounded_identifier(quantity_id):
            continue
        previous_symbol = claimed_quantities.get(quantity_id)
        if previous_symbol is not None and previous_symbol != symbol_id:
            _add_issue(
                issues,
                MechanicsIssueCode.symbol_quantity_mismatch,
                "one quantity cannot be bound to multiple symbols",
                f"{path}.quantity_id",
                referenced_id=quantity_id,
            )
        elif _bounded_identifier(symbol_id):
            claimed_quantities[quantity_id] = symbol_id
        quantity = quantities.get(quantity_id)
        if quantity is None:
            continue
        if getattr(quantity, "symbol_id", None) != symbol_id:
            _add_issue(
                issues,
                MechanicsIssueCode.symbol_quantity_mismatch,
                "symbol.quantity_id must be reciprocated by quantity.symbol_id",
                f"{path}.quantity_id",
                referenced_id=quantity_id,
            )

    for index, quantity in enumerate(quantity_items):
        path = f"quantities.{index}"
        quantity_id = getattr(quantity, "quantity_id", None)
        symbol_id = getattr(quantity, "symbol_id", None)
        if not _bounded_identifier(symbol_id):
            continue
        symbol = symbols.get(symbol_id)
        if symbol is None:
            continue
        if getattr(symbol, "quantity_id", None) != quantity_id:
            _add_issue(
                issues,
                MechanicsIssueCode.symbol_quantity_mismatch,
                "quantity.symbol_id must be reciprocated by symbol.quantity_id",
                f"{path}.symbol_id",
                referenced_id=symbol_id,
            )
        if getattr(symbol, "dimension", None) != getattr(quantity, "dimension", None):
            _add_issue(
                issues,
                MechanicsIssueCode.symbol_quantity_mismatch,
                "symbol and quantity dimensions must be identical",
                f"{path}.symbol_id",
                referenced_id=symbol_id,
            )
        quantity_shape = _enum_value(getattr(quantity, "shape", None))
        symbol_shape = _enum_value(getattr(symbol, "shape", None))
        vector_length = getattr(symbol, "vector_length", None)
        if quantity_shape == "tensor":
            _add_issue(
                issues,
                MechanicsIssueCode.symbol_quantity_mismatch,
                "tensor quantities cannot bind to the scalar/vector math AST symbol table",
                f"{path}.symbol_id",
                referenced_id=symbol_id,
            )
        elif quantity_shape == "scalar":
            if symbol_shape != "scalar" or vector_length is not None:
                _add_issue(
                    issues,
                    MechanicsIssueCode.symbol_quantity_mismatch,
                    "scalar quantities require scalar symbols without vector_length",
                    f"{path}.symbol_id",
                    referenced_id=symbol_id,
                )
        elif quantity_shape == "vector":
            if (
                symbol_shape != "vector"
                or type(vector_length) is not int
                or not 2 <= vector_length <= 8
            ):
                _add_issue(
                    issues,
                    MechanicsIssueCode.symbol_quantity_mismatch,
                    "vector quantities require a bounded vector symbol",
                    f"{path}.symbol_id",
                    referenced_id=symbol_id,
                )
            direction = getattr(quantity, "direction", None)
            if _enum_value(getattr(direction, "kind", None)) == "vector":
                components = _snapshot(
                    getattr(direction, "components", None),
                    limit=8,
                    path=f"{path}.direction.components",
                    issues=issues,
                )
                if type(vector_length) is int and len(components) != vector_length:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.symbol_quantity_mismatch,
                        "vector direction component count must equal symbol.vector_length",
                        f"{path}.direction.components",
                        referenced_id=symbol_id,
                    )


def _vector_binding_is_trusted(
    quantity: object,
    symbols: Mapping[str, object],
    *,
    component_count: int,
) -> bool:
    symbol_id = getattr(quantity, "symbol_id", None)
    if not _bounded_identifier(symbol_id):
        return False
    symbol = symbols.get(symbol_id)
    return (
        type(symbol) is SymbolDefinition
        and _enum_value(getattr(symbol, "shape", None)) == "vector"
        and type(getattr(symbol, "vector_length", None)) is int
        and getattr(symbol, "vector_length", None) == component_count
        and getattr(symbol, "dimension", None) == getattr(quantity, "dimension", None)
        and getattr(symbol, "quantity_id", None) == getattr(quantity, "quantity_id", None)
    )


def _validate_quantity_provenance(
    quantities: tuple[object, ...],
    evidence: Mapping[str, object],
    text_facts: Mapping[str, _TextEvidenceFacts],
    figure_facts: Mapping[str, _FigureEvidenceFacts],
    assumptions: Mapping[str, object],
    symbols: Mapping[str, object],
    authorized_corrections: Mapping[str, object],
    authorized_assumptions: Mapping[str, object],
    approved_assumption_ids: set[str],
    confirmed_figure_evidence_ids: set[str],
    *,
    issues: list[MechanicsValidationIssue],
) -> bool:
    """Validate raw-fact provenance and report confirmation-only evidence."""

    needs_confirmation = False
    used_occurrences: dict[tuple[object, ...], str] = {}
    for index, quantity in enumerate(quantities):
        path = f"quantities.{index}"
        quantity_id = getattr(quantity, "quantity_id", None)
        raw_value = getattr(quantity, "raw_value", None)
        raw_unit = getattr(quantity, "raw_unit", None)
        pair_has_any_member = raw_value is not None or raw_unit is not None
        raw_value_is_valid = raw_value is None or _bounded_string(
            raw_value,
            maximum=_MAX_RAW_VALUE_LENGTH,
        )
        raw_unit_is_valid = raw_unit is None or _bounded_string(
            raw_unit,
            maximum=_MAX_RAW_UNIT_LENGTH,
            allow_empty=True,
        )
        if not raw_value_is_valid:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "raw_value must be an exact non-empty string of at most 80 characters",
                f"{path}.raw_value",
            )
        if not raw_unit_is_valid:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "raw_unit must be an exact string of at most 48 characters",
                f"{path}.raw_unit",
            )
        pair_complete = (
            raw_value is not None
            and raw_unit is not None
            and raw_value_is_valid
            and raw_unit_is_valid
        )
        provenance = _enum_value(getattr(quantity, "provenance", None))
        shape = _enum_value(getattr(quantity, "shape", None))
        evidence_refs = _references(quantity, "evidence_refs", path=path, issues=issues)
        validated_vector_expected: tuple[tuple[str, str], ...] = ()
        vector_binding_trusted: bool | None = None

        if pair_complete and shape == "scalar" and _canonical_pair(raw_value, raw_unit) is None:
            pair_complete = False
            _add_issue(
                issues,
                MechanicsIssueCode.provenance_violation,
                "scalar raw value/unit must be one complete numeric token and one adjacent complete unit token",
                path,
            )
        elif pair_complete and shape == "vector":
            vector_expected, vector_is_unsafe = _expected_numeric_pairs(
                quantity,
                raw_value,
                raw_unit,
            )
            if vector_is_unsafe or not vector_expected:
                pair_complete = False
                _add_issue(
                    issues,
                    MechanicsIssueCode.numeric_sequence_unconfirmed,
                    "vector raw values require a complete two- or three-component comma-separated numeric sequence",
                    path,
                    severity=MechanicsIssueSeverity.warning,
                )
                needs_confirmation = True
            else:
                validated_vector_expected = vector_expected
                vector_binding_trusted = _vector_binding_is_trusted(
                    quantity,
                    symbols,
                    component_count=len(vector_expected),
                )
                if not vector_binding_trusted:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.numeric_sequence_unconfirmed,
                        "vector raw values require an exact reciprocal vector symbol, length, and dimension binding",
                        path,
                        severity=MechanicsIssueSeverity.warning,
                    )
                    needs_confirmation = True
        elif (
            pair_complete
            and shape == "tensor"
            and provenance in {"explicit_source", "user_correction", "server_default"}
        ):
            _add_issue(
                issues,
                MechanicsIssueCode.numeric_sequence_unconfirmed,
                "tensor raw values remain confirmation-only until a structured tensor grammar is available",
                path,
                severity=MechanicsIssueSeverity.warning,
            )
            needs_confirmation = True
        elif pair_complete and shape not in {"scalar", "vector", "tensor"}:
            pair_complete = False
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "raw numeric facts require a recognized scalar, vector, or tensor shape",
                f"{path}.shape",
            )
        if pair_has_any_member and not pair_complete:
            _add_issue(
                issues,
                MechanicsIssueCode.provenance_violation,
                "raw_value and raw_unit must be supplied as one bounded valid pair",
                path,
            )

        if provenance == "explicit_source":
            if not pair_complete:
                _add_issue(
                    issues,
                    MechanicsIssueCode.provenance_violation,
                    "explicit_source quantities require a valid raw value/unit pair",
                    path,
                )
                continue
            if shape == "tensor":
                continue

            if shape == "vector":
                expected, unsafe_sequence = validated_vector_expected, False
            else:
                expected, unsafe_sequence = _expected_numeric_pairs(
                    quantity,
                    raw_value,
                    raw_unit,
                )
            if unsafe_sequence or not expected:
                _add_issue(
                    issues,
                    MechanicsIssueCode.numeric_sequence_unconfirmed,
                    "raw values require an explicit canonical source token sequence",
                    path,
                    severity=MechanicsIssueSeverity.warning,
                )
                needs_confirmation = True
                continue
            value_seen = False
            unit_seen = False
            ambiguous_binding = False
            trusted_bindings: list[_NumericBinding] = []
            unconfirmed_figure_bindings: list[_NumericBinding] = []
            for ref in evidence_refs:
                if not _bounded_identifier(ref):
                    continue
                source_item = evidence.get(ref)
                if source_item is None:
                    continue
                source_kind = _enum_value(getattr(source_item, "kind", None))
                if source_kind == "text":
                    fact = text_facts.get(ref)
                    tokens = fact.tokens if fact is not None else ()
                    values, units = _evidence_presence(expected, tokens)
                    value_seen = value_seen or values
                    unit_seen = unit_seen or units
                    if fact is not None and fact.quantity_start is not None:
                        binding, ambiguous = _binding_from_tokens(
                            expected,
                            tokens,
                            identity_prefix=("text",),
                            absolute_offset=fact.quantity_start,
                        )
                        ambiguous_binding = ambiguous_binding or ambiguous
                        if binding is not None:
                            trusted_bindings.append(binding)
                elif source_kind == "figure":
                    fact = figure_facts.get(ref)
                    tokens = fact.tokens if fact is not None else ()
                    values, units = _evidence_presence(expected, tokens)
                    value_seen = value_seen or values
                    unit_seen = unit_seen or units
                    if fact is not None and fact.identity_prefix is not None:
                        binding, ambiguous = _binding_from_tokens(
                            expected,
                            tokens,
                            identity_prefix=fact.identity_prefix,
                            absolute_offset=0,
                            unconfirmed_figure=ref not in confirmed_figure_evidence_ids,
                        )
                        ambiguous_binding = ambiguous_binding or ambiguous
                        if binding is not None:
                            if binding.unconfirmed_figure:
                                unconfirmed_figure_bindings.append(binding)
                            else:
                                trusted_bindings.append(binding)

            if not value_seen:
                _add_issue(
                    issues,
                    MechanicsIssueCode.raw_value_mismatch,
                    "raw_value is not present as a canonical numeric token",
                    f"{path}.raw_value",
                )
            if not unit_seen:
                _add_issue(
                    issues,
                    MechanicsIssueCode.raw_unit_mismatch,
                    "raw_unit is not present as an adjacent canonical unit token",
                    f"{path}.raw_unit",
                )

            too_many_bindings = (
                len(trusted_bindings) > 1
                or (not trusted_bindings and len(unconfirmed_figure_bindings) > 1)
            )
            selected_binding: _NumericBinding | None = None
            if not ambiguous_binding and not too_many_bindings:
                if len(trusted_bindings) == 1:
                    selected_binding = trusted_bindings[0]
                elif len(unconfirmed_figure_bindings) == 1:
                    selected_binding = unconfirmed_figure_bindings[0]

            if selected_binding is not None:
                _claim_numeric_binding(
                    selected_binding,
                    quantity_id,
                    path=path,
                    used_occurrences=used_occurrences,
                    issues=issues,
                )
                if selected_binding.unconfirmed_figure:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.figure_evidence_unconfirmed,
                        "numeric figure evidence requires explicit trusted confirmation",
                        path,
                        severity=MechanicsIssueSeverity.warning,
                    )
                    needs_confirmation = True
            elif ambiguous_binding or too_many_bindings:
                _add_issue(
                    issues,
                    MechanicsIssueCode.numeric_sequence_unconfirmed,
                    "numeric evidence has multiple valid or non-canonical candidate bindings",
                    path,
                    severity=MechanicsIssueSeverity.warning,
                )
                needs_confirmation = True
            else:
                _add_issue(
                    issues,
                    MechanicsIssueCode.invented_explicit_number,
                    "explicit_source quantity is not grounded by one exact numeric token binding",
                    path,
                )
        elif provenance == "user_correction":
            correction_id = getattr(quantity, "correction_id", None)
            authorization = (
                authorized_corrections.get(correction_id)
                if _bounded_identifier(correction_id)
                else None
            )
            if (
                not pair_complete
                or not _bounded_identifier(correction_id)
                or not _authorization_matches(
                    quantity,
                    authorization,
                    raw_value=raw_value,
                    raw_unit=raw_unit,
                    correction=True,
                )
            ):
                _add_issue(
                    issues,
                    MechanicsIssueCode.provenance_violation,
                    "user_correction requires one exact immutable correction authorization",
                    path,
                    referenced_id=correction_id if _bounded_identifier(correction_id) else None,
                )
        elif provenance == "server_default":
            policy_ref = getattr(quantity, "assumption_policy_ref", None)
            policy = assumptions.get(policy_ref) if _bounded_identifier(policy_ref) else None
            authorization = (
                authorized_assumptions.get(policy_ref)
                if _bounded_identifier(policy_ref)
                else None
            )
            if (
                not pair_complete
                or not _bounded_identifier(policy_ref)
                or policy_ref not in approved_assumption_ids
                or policy is None
                or _enum_value(getattr(policy, "disposition", None)) == "rejected"
                or not _authorization_matches(
                    quantity,
                    authorization,
                    raw_value=raw_value,
                    raw_unit=raw_unit,
                    correction=False,
                )
            ):
                _add_issue(
                    issues,
                    MechanicsIssueCode.provenance_violation,
                    "server_default requires both explicit approval and one exact immutable assumption authorization",
                    path,
                    referenced_id=policy_ref if _bounded_identifier(policy_ref) else None,
                )
        elif provenance in {"inferred", "unknown"}:
            if pair_has_any_member:
                _add_issue(
                    issues,
                    MechanicsIssueCode.provenance_violation,
                    "inferred and unknown quantities cannot carry raw numeric facts",
                    path,
                )
        else:
            _add_issue(
                issues,
                MechanicsIssueCode.schema_error,
                "quantity provenance is not recognized",
                f"{path}.provenance",
            )
    return needs_confirmation

def _validate_query_binding(
    query: object,
    quantity: object,
    *,
    path: str,
    issues: list[MechanicsValidationIssue],
) -> None:
    target = getattr(query, "target", None)
    if target is None:
        _add_issue(
            issues,
            MechanicsIssueCode.query_binding_invalid,
            "query has no target binding",
            f"{path}.target",
        )
        return
    mismatches = (
        ("role", getattr(target, "role", None), getattr(quantity, "role", None)),
        ("subject_id", getattr(target, "subject_id", None), getattr(quantity, "subject_id", None)),
        ("shape", getattr(query, "shape", None), getattr(quantity, "shape", None)),
        ("output_dimension", getattr(query, "output_dimension", None), getattr(quantity, "dimension", None)),
    )
    for field, expected, actual in mismatches:
        if expected != actual:
            _add_issue(
                issues,
                MechanicsIssueCode.query_binding_invalid,
                "target_quantity_id conflicts with the query binding",
                f"{path}.{field}",
            )
    for field in ("point_id", "frame_id", "interval_id", "event_id"):
        target_value = getattr(target, field, None)
        if target_value is not None and target_value != getattr(quantity, field, None):
            _add_issue(
                issues,
                MechanicsIssueCode.query_binding_invalid,
                "target_quantity_id conflicts with an explicit target scope",
                f"{path}.target.{field}",
            )
    target_component = _enum_value(getattr(target, "component", None))
    if target_component not in {None, "unspecified"} and getattr(target, "component", None) != getattr(quantity, "component", None):
        _add_issue(
            issues,
            MechanicsIssueCode.query_binding_invalid,
            "target_quantity_id conflicts with the target component",
            f"{path}.target.component",
        )
    target_direction = getattr(target, "direction", None)
    if target_direction is not None and target_direction != getattr(quantity, "direction", None):
        _add_issue(
            issues,
            MechanicsIssueCode.query_binding_invalid,
            "target_quantity_id conflicts with the target direction",
            f"{path}.target.direction",
        )


def _map_ast_issues(
    ast_issues: tuple[AstValidationIssue, ...],
    *,
    issues: list[MechanicsValidationIssue],
) -> None:
    for ast_issue in ast_issues:
        _add_issue(
            issues,
            _AST_CODES.get(ast_issue.code, MechanicsIssueCode.ast_unsupported),
            ast_issue.message,
            ast_issue.path,
            referenced_id=ast_issue.referenced_id,
        )


def validate_draft(
    problem_text: str,
    draft: MechanicsProblemDraftV1,
    *,
    approved_assumption_ids: Collection[str] = (),
    authorized_corrections: Mapping[str, CorrectionAuthorization] = {},
    authorized_assumptions: Mapping[str, AssumptionAuthorization] = {},
    confirmed_figure_evidence_ids: Collection[str] = (),
) -> DraftValidationResult:
    """Validate a draft without interpreting problem text as mathematics.

    The only use of ``problem_text`` is exact evidence quote/span verification.
    Any malformed collection or unresolved graph reference is an error and takes
    precedence over non-error terminals.
    """

    issues: list[MechanicsValidationIssue] = []
    if not isinstance(draft, MechanicsProblemDraftV1):
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "draft must be a MechanicsProblemDraftV1 instance",
            "draft",
        )
        return DraftValidationResult(ValidationTerminal.invalid, tuple(issues))

    try:
        approved_ids = _approved_ids(approved_assumption_ids, issues=issues)
        correction_authorizations = _trusted_authorization_map(
            authorized_corrections,
            CorrectionAuthorization,
            "correction_id",
            path="authorized_corrections",
            issues=issues,
        )
        assumption_authorizations = _trusted_authorization_map(
            authorized_assumptions,
            AssumptionAuthorization,
            "assumption_id",
            path="authorized_assumptions",
            issues=issues,
        )
        confirmed_figure_ids = _trusted_ids(
            confirmed_figure_evidence_ids,
            path="confirmed_figure_evidence_ids",
            issues=issues,
        )
        collections: dict[str, tuple[object, ...]] = {}
        namespaces: dict[str, dict[str, object]] = {}
        for attribute, id_attribute, limit, namespace in _COLLECTION_SPECS:
            values = _snapshot(
                getattr(draft, attribute, None),
                limit=limit,
                path=attribute,
                issues=issues,
            )
            collections[attribute] = values
            namespaces[namespace] = _index_namespace(
                values,
                id_attribute=id_attribute,
                path=attribute,
                issues=issues,
            )

        assets = namespaces["asset"]
        evidence = namespaces["evidence"]
        entities = namespaces["entity"]
        points = namespaces["point"]
        frames = namespaces["frame"]
        intervals = namespaces["interval"]
        events = namespaces["event"]
        symbols = namespaces["symbol"]
        quantities = namespaces["quantity"]
        assumptions = namespaces["assumption"]
        all_graph_ids = _index_global_namespaces(collections, issues=issues)
        participants = set(entities) | set(points)

        for evidence_id in confirmed_figure_ids:
            confirmed_evidence = evidence.get(evidence_id)
            if _enum_value(getattr(confirmed_evidence, "kind", None)) != "figure":
                _add_issue(
                    issues,
                    MechanicsIssueCode.schema_error,
                    "confirmed figure evidence ID must resolve to a figure evidence record",
                    "confirmed_figure_evidence_ids",
                    referenced_id=evidence_id,
                )

        text_facts = _validate_text_evidence(
            problem_text,
            collections["source_evidence"],
            issues=issues,
        )

        for index, asset in enumerate(collections["source_assets"]):
            path = f"source_assets.{index}"
            _optional_reference(
                getattr(asset, "parent_asset_id", None),
                assets,
                path=f"{path}.parent_asset_id",
                issues=issues,
            )
            _validate_asset_page_topology(asset, assets, path=path, issues=issues)
        figure_facts = _validate_figure_evidence(
            collections["source_evidence"],
            assets,
            issues=issues,
        )

        for index, entity in enumerate(collections["entities"]):
            path = f"entities.{index}"
            _optional_reference(getattr(entity, "component_of_entity_id", None), entities, path=f"{path}.component_of_entity_id", issues=issues)
            _validate_reference_list(entity, "evidence_refs", evidence, path=path, issues=issues)

        for index, point in enumerate(collections["points"]):
            path = f"points.{index}"
            _optional_reference(getattr(point, "owner_entity_id", None), entities, path=f"{path}.owner_entity_id", issues=issues)
            _optional_reference(getattr(point, "frame_id", None), frames, path=f"{path}.frame_id", issues=issues)
            _validate_reference_list(point, "evidence_refs", evidence, path=path, issues=issues)

        for index, frame in enumerate(collections["reference_frames"]):
            path = f"reference_frames.{index}"
            _validate_frame_origin(
                getattr(frame, "origin", None),
                path=f"{path}.origin",
                entities=entities,
                points=points,
                frames=frames,
                issues=issues,
            )
            axes = _snapshot(getattr(frame, "axes", None), limit=3, path=f"{path}.axes", issues=issues)
            for axis_index, axis in enumerate(axes):
                _validate_direction(
                    getattr(axis, "direction", None),
                    path=f"{path}.axes.{axis_index}.direction",
                    frames=frames,
                    symbols=symbols,
                    issues=issues,
                )
            _optional_reference(getattr(frame, "parent_frame_id", None), frames, path=f"{path}.parent_frame_id", issues=issues)
            _optional_reference(getattr(frame, "translating_with_entity_id", None), entities, path=f"{path}.translating_with_entity_id", issues=issues)
            _optional_reference(getattr(frame, "rotating_about_point_id", None), points, path=f"{path}.rotating_about_point_id", issues=issues)
            _validate_reference_list(frame, "generalized_coordinate_symbol_ids", symbols, path=path, issues=issues)
            _validate_reference_list(frame, "evidence_refs", evidence, path=path, issues=issues)

        for index, interval in enumerate(collections["motion_intervals"]):
            path = f"motion_intervals.{index}"
            _validate_reference_list(interval, "subject_ids", entities, path=path, issues=issues)
            _optional_reference(getattr(interval, "frame_id", None), frames, path=f"{path}.frame_id", issues=issues)
            _optional_reference(getattr(interval, "start_event_id", None), events, path=f"{path}.start_event_id", issues=issues)
            _optional_reference(getattr(interval, "end_event_id", None), events, path=f"{path}.end_event_id", issues=issues)
            _validate_reference_list(interval, "evidence_refs", evidence, path=path, issues=issues)

        for index, event in enumerate(collections["events"]):
            path = f"events.{index}"
            _validate_reference_list(event, "subject_ids", entities, path=path, issues=issues)
            _validate_reference_list(event, "interval_ids", intervals, path=path, issues=issues)
            time_quantity_id = getattr(event, "time_quantity_id", None)
            if _optional_reference(time_quantity_id, quantities, path=f"{path}.time_quantity_id", issues=issues) and time_quantity_id is not None:
                time_quantity = quantities.get(time_quantity_id) if isinstance(time_quantity_id, str) else None
                if _enum_value(getattr(time_quantity, "role", None)) not in {"time", "duration"}:
                    _add_issue(
                        issues,
                        MechanicsIssueCode.interval_event_invalid,
                        "event time_quantity_id must identify a time or duration quantity",
                        f"{path}.time_quantity_id",
                        referenced_id=time_quantity_id if isinstance(time_quantity_id, str) else None,
                    )
            _validate_reference_list(event, "evidence_refs", evidence, path=path, issues=issues)

        for index, symbol in enumerate(collections["symbols"]):
            path = f"symbols.{index}"
            _optional_reference(getattr(symbol, "quantity_id", None), quantities, path=f"{path}.quantity_id", issues=issues)

        for index, quantity in enumerate(collections["quantities"]):
            path = f"quantities.{index}"
            _optional_reference(getattr(quantity, "symbol_id", None), symbols, path=f"{path}.symbol_id", issues=issues)
            _reference(getattr(quantity, "subject_id", None), entities, path=f"{path}.subject_id", issues=issues)
            _optional_reference(getattr(quantity, "point_id", None), points, path=f"{path}.point_id", issues=issues)
            _optional_reference(getattr(quantity, "frame_id", None), frames, path=f"{path}.frame_id", issues=issues)
            _optional_reference(getattr(quantity, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _optional_reference(getattr(quantity, "event_id", None), events, path=f"{path}.event_id", issues=issues)
            _validate_direction(getattr(quantity, "direction", None), path=f"{path}.direction", frames=frames, symbols=symbols, issues=issues)
            _validate_reference_list(quantity, "evidence_refs", evidence, path=path, issues=issues)
            _optional_reference(getattr(quantity, "assumption_policy_ref", None), assumptions, path=f"{path}.assumption_policy_ref", issues=issues)

        _validate_symbol_quantity_bindings(
            collections["symbols"],
            collections["quantities"],
            symbols,
            quantities,
            issues=issues,
        )

        for index, relation in enumerate(collections["geometry"]):
            path = f"geometry.{index}"
            _validate_reference_list(relation, "participant_ids", participants, path=path, issues=issues)
            _validate_reference_list(relation, "quantity_ids", quantities, path=path, issues=issues)
            _optional_reference(getattr(relation, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _validate_reference_list(relation, "evidence_refs", evidence, path=path, issues=issues)

        for index, interaction in enumerate(collections["interactions"]):
            path = f"interactions.{index}"
            _validate_reference_list(interaction, "participant_ids", participants, path=path, issues=issues)
            _validate_reference_list(interaction, "point_ids", points, path=path, issues=issues)
            _optional_reference(getattr(interaction, "frame_id", None), frames, path=f"{path}.frame_id", issues=issues)
            _optional_reference(getattr(interaction, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _optional_reference(getattr(interaction, "event_id", None), events, path=f"{path}.event_id", issues=issues)
            _validate_reference_list(interaction, "quantity_ids", quantities, path=path, issues=issues)
            _validate_reference_list(interaction, "evidence_refs", evidence, path=path, issues=issues)

        for index, constraint in enumerate(collections["constraints"]):
            path = f"constraints.{index}"
            _validate_reference_list(constraint, "subject_ids", entities, path=path, issues=issues)
            _optional_reference(getattr(constraint, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _optional_reference(getattr(constraint, "event_id", None), events, path=f"{path}.event_id", issues=issues)
            _validate_reference_list(constraint, "evidence_refs", evidence, path=path, issues=issues)

        for index, state in enumerate(collections["state_conditions"]):
            path = f"state_conditions.{index}"
            _reference(getattr(state, "subject_id", None), entities, path=f"{path}.subject_id", issues=issues)
            _optional_reference(getattr(state, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _optional_reference(getattr(state, "event_id", None), events, path=f"{path}.event_id", issues=issues)
            _validate_reference_list(state, "quantity_ids", quantities, path=path, issues=issues)
            _validate_reference_list(state, "evidence_refs", evidence, path=path, issues=issues)

        for index, query in enumerate(collections["queries"]):
            path = f"queries.{index}"
            target = getattr(query, "target", None)
            if target is None:
                _add_issue(issues, MechanicsIssueCode.query_binding_invalid, "query has no target", f"{path}.target")
            else:
                _reference(getattr(target, "subject_id", None), entities, path=f"{path}.target.subject_id", issues=issues)
                _optional_reference(getattr(target, "point_id", None), points, path=f"{path}.target.point_id", issues=issues)
                _optional_reference(getattr(target, "frame_id", None), frames, path=f"{path}.target.frame_id", issues=issues)
                _optional_reference(getattr(target, "interval_id", None), intervals, path=f"{path}.target.interval_id", issues=issues)
                _optional_reference(getattr(target, "event_id", None), events, path=f"{path}.target.event_id", issues=issues)
                _validate_direction(getattr(target, "direction", None), path=f"{path}.target.direction", frames=frames, symbols=symbols, issues=issues)
                target_quantity_id = getattr(target, "target_quantity_id", None)
                if _optional_reference(target_quantity_id, quantities, path=f"{path}.target.target_quantity_id", issues=issues) and target_quantity_id is not None:
                    target_quantity = quantities.get(target_quantity_id) if isinstance(target_quantity_id, str) else None
                    if target_quantity is not None:
                        _validate_query_binding(query, target_quantity, path=path, issues=issues)
            _validate_reference_list(query, "evidence_refs", evidence, path=path, issues=issues)

        for index, hint in enumerate(collections["principle_hints"]):
            path = f"principle_hints.{index}"
            _validate_reference_list(hint, "scope_ids", all_graph_ids, path=path, issues=issues)
            _validate_reference_list(hint, "evidence_refs", evidence, path=path, issues=issues)

        unapproved_assumptions = False
        for index, assumption in enumerate(collections["assumptions"]):
            path = f"assumptions.{index}"
            _reference(getattr(assumption, "subject_id", None), entities, path=f"{path}.subject_id", issues=issues)
            _optional_reference(getattr(assumption, "interval_id", None), intervals, path=f"{path}.interval_id", issues=issues)
            _validate_reference_list(assumption, "evidence_refs", evidence, path=path, issues=issues)
            disposition = _enum_value(getattr(assumption, "disposition", None))
            assumption_id = getattr(assumption, "assumption_id", None)
            if (
                disposition in {"proposed", "visible", "approved"}
                and assumption_id not in approved_ids
            ):
                unapproved_assumptions = True
                _add_issue(
                    issues,
                    MechanicsIssueCode.assumption_not_approved,
                    "every non-rejected model-authored assumption requires explicit external approval",
                    path,
                    severity=MechanicsIssueSeverity.warning,
                    referenced_id=assumption_id if isinstance(assumption_id, str) else None,
                )

        for index, ambiguity in enumerate(collections["ambiguities"]):
            path = f"ambiguities.{index}"
            _validate_reference_list(ambiguity, "referenced_ids", all_graph_ids, path=path, issues=issues)
            _validate_reference_list(ambiguity, "evidence_refs", evidence, path=path, issues=issues)

        figure_dependency = getattr(draft, "figure_dependency", None)
        if figure_dependency is None:
            _add_issue(issues, MechanicsIssueCode.schema_error, "figure_dependency is missing", "figure_dependency")
            figure_level = None
        else:
            figure_level = _enum_value(getattr(figure_dependency, "level", None))
            _validate_reference_list(figure_dependency, "evidence_refs", evidence, path="figure_dependency", issues=issues)

        for index, unsupported in enumerate(collections["unsupported_features"]):
            path = f"unsupported_features.{index}"
            _validate_reference_list(unsupported, "referenced_ids", all_graph_ids, path=path, issues=issues)
            _validate_reference_list(unsupported, "evidence_refs", evidence, path=path, issues=issues)

        provenance_needs_confirmation = _validate_quantity_provenance(
            collections["quantities"],
            evidence,
            text_facts,
            figure_facts,
            assumptions,
            symbols,
            correction_authorizations,
            assumption_authorizations,
            approved_ids,
            confirmed_figure_ids,
            issues=issues,
        )

        expressions: list[tuple[str, object]] = []
        for collection_name in ("geometry", "constraints", "state_conditions"):
            for index, item in enumerate(collections[collection_name]):
                expression = getattr(item, "expression", None)
                if expression is not None:
                    expressions.append((f"{collection_name}.{index}.expression", expression))
        try:
            ast_issues = validate_math_expressions(expressions, symbols)  # exactly one aggregate gate
        except Exception:
            _add_issue(
                issues,
                MechanicsIssueCode.ast_unsupported,
                "math expression aggregate validation failed closed",
                "expressions",
            )
        else:
            _map_ast_issues(ast_issues, issues=issues)
    except Exception:
        _add_issue(
            issues,
            MechanicsIssueCode.schema_error,
            "draft validation failed closed while inspecting the graph",
            "draft",
        )
        return DraftValidationResult(ValidationTerminal.invalid, tuple(issues))

    has_error = any(
        issue.severity in {MechanicsIssueSeverity.error, MechanicsIssueSeverity.critical}
        for issue in issues
    )
    if has_error:
        terminal = ValidationTerminal.invalid
    elif figure_level == "required":
        terminal = ValidationTerminal.needs_figure
    elif collections["unsupported_features"]:
        terminal = ValidationTerminal.unsupported
    elif collections["ambiguities"] or unapproved_assumptions or provenance_needs_confirmation:
        terminal = ValidationTerminal.needs_confirmation
    elif not collections["queries"]:
        terminal = ValidationTerminal.insufficient_information
    else:
        terminal = ValidationTerminal.accepted
    return DraftValidationResult(terminal=terminal, issues=tuple(issues))


__all__ = [
    "AssumptionAuthorization",
    "CorrectionAuthorization",
    "DraftValidationResult",
    "ValidationTerminal",
    "validate_draft",
]
