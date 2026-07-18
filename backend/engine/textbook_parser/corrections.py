from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.textbook_parser.contracts import TextbookProblemParseV1


CORRECTION_POLICY_VERSION = "textbook-correction-v2"
_ID_FIELDS = {
    "entities": "entity_id",
    "motion_segments": "segment_id",
    "events": "event_id",
    "explicit_facts": "fact_id",
    "relations": "relation_id",
    "queries": "query_id",
    "assumption_proposals": "assumption_id",
    "interpretation_candidates": "candidate_id",
}
_ALLOWED_FIELDS = {
    "entities": {"kind", "label", "aliases"},
    "motion_segments": {"order", "actor_ids", "motion_model_candidates", "start_event_id", "end_event_id", "relevance"},
    "events": {"kind", "subject_ids", "segment_id"},
    "explicit_facts": {"semantic_key", "subject_id", "segment_id", "event_id", "temporal_role", "direction", "relevance"},
    "relations": {"kind", "entity_ids", "segment_id"},
    "queries": {"output_key", "subject_id", "segment_id", "event_id", "component"},
    "assumption_proposals": {"kind", "subject_id", "segment_id", "proposed_semantic_key", "proposed_value", "proposed_unit", "reason"},
    "interpretation_candidates": {"system_type", "subtype", "target_segment_ids", "fact_ids", "query_ids", "assumption_ids", "reason_code"},
}


def apply_parse_corrections(
    parse: TextbookProblemParseV1, patch: dict[str, Any]
) -> TextbookProblemParseV1:
    """Apply bounded structural edits, then rerun the full schema/gate externally.

    Explicit values, units, and source evidence are immutable in this graph patch.
    Every accepted correction is revision-bound and must pass the same authoritative
    schema, evidence, assumption, binding, capability, and safe-solver gates.
    """

    if set(patch) != {"operations"} or not isinstance(patch["operations"], list):
        raise ValueError("textbook parse correction must contain only an operations list")
    if len(patch["operations"]) > 24:
        raise ValueError("too many textbook parse correction operations")
    payload = deepcopy(parse.model_dump(mode="json"))
    for operation in patch["operations"]:
        if not isinstance(operation, dict) or set(operation) != {"collection", "id", "set"}:
            raise ValueError("each correction requires collection, id, and set")
        collection = operation["collection"]
        target_id = operation["id"]
        updates = operation["set"]
        if collection not in _ID_FIELDS or not isinstance(updates, dict) or not updates:
            raise ValueError("unknown or empty correction collection")
        unknown = set(updates) - _ALLOWED_FIELDS[collection]
        if unknown:
            raise ValueError(
                f"correction fields are not whitelisted for {collection}: {sorted(unknown)}"
            )
        id_field = _ID_FIELDS[collection]
        target = next(
            (item for item in payload[collection] if item[id_field] == target_id),
            None,
        )
        if target is None:
            raise ValueError(f"correction target does not exist: {collection}.{target_id}")
        target.update(deepcopy(updates))
    return TextbookProblemParseV1.model_validate(payload)


__all__ = ["CORRECTION_POLICY_VERSION", "apply_parse_corrections"]
