from __future__ import annotations

import json
from pathlib import Path

from engine.textbook_parser.contracts import (
    AssumptionKind,
    EventKind,
    MotionModel,
    QueryOutputKey,
    RelationKind,
)
from engine.textbook_parser.legal_fixtures import (
    PROMPT_EXAMPLE_FIXTURE_IDS,
    legal_graph_fixtures,
)
from engine.textbook_parser.ontology import (
    ExplicitSemanticKey,
    ParserSystemType,
)


PROMPT_VERSION = "textbook-parser-v3-generated"
PROMPT_PATH = Path(__file__).with_name("prompts") / "textbook_parser_v3.txt"


def _values(enum_type) -> list[str]:
    return [item.value for item in enum_type]


def generated_vocabulary() -> dict[str, list[str]]:
    return {
        "system_types": _values(ParserSystemType),
        "semantic_keys": _values(ExplicitSemanticKey),
        "motion_models": _values(MotionModel),
        "event_kinds": _values(EventKind),
        "relation_kinds": _values(RelationKind),
        "query_output_keys": _values(QueryOutputKey),
        "assumption_kinds": _values(AssumptionKind),
    }


def _compact_example(fixture) -> dict[str, object]:
    parse = fixture.parse
    return {
        "fixture": fixture.fixture_id,
        "parse_status": parse.parse_status.value,
        "entities": [
            {"id": item.entity_id, "kind": item.kind.value}
            for item in parse.entities
        ],
        "segments": [
            {
                "id": item.segment_id,
                "actors": list(item.actor_ids),
                "motion_models": [value.value for value in item.motion_model_candidates],
                "start": item.start_event_id,
                "end": item.end_event_id,
            }
            for item in parse.motion_segments
        ],
        "events": [
            {"id": item.event_id, "kind": item.kind.value}
            for item in parse.events
        ],
        "facts": [
            {
                "id": item.fact_id,
                "semantic_key": item.semantic_key.value,
                "subject": item.subject_id,
                "segment": item.segment_id,
                "event": item.event_id,
                "temporal_role": item.temporal_role.value,
            }
            for item in parse.explicit_facts
        ],
        "relations": [
            {
                "kind": item.kind.value,
                "entities": list(item.entity_ids),
                "segment": item.segment_id,
            }
            for item in parse.relations
        ],
        "queries": [
            {
                "output": item.output_key.value,
                "subject": item.subject_id,
                "segment": item.segment_id,
            }
            for item in parse.queries
        ],
        "assumptions": [item.kind.value for item in parse.assumption_proposals],
        "candidates": [
            {
                "system_type": item.system_type.value,
                "targets": list(item.target_segment_ids),
                "facts": list(item.fact_ids),
                "queries": list(item.query_ids),
                "assumptions": list(item.assumption_ids),
            }
            for item in parse.interpretation_candidates
        ],
        "figure_dependency": parse.figure_dependency.level.value,
    }


def generated_examples() -> list[dict[str, object]]:
    by_id = {item.fixture_id: item for item in legal_graph_fixtures()}
    return [_compact_example(by_id[item]) for item in PROMPT_EXAMPLE_FIXTURE_IDS]


def load_prompt() -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8").rstrip()
    vocabulary = json.dumps(
        generated_vocabulary(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    examples = json.dumps(
        generated_examples(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return (
        base
        + "\n\nGenerated controlled vocabulary (authoritative):\n"
        + vocabulary
        + "\n\nCompact schema-validated structural examples (inputs and structure only):\n"
        + examples
        + "\n"
    )


__all__ = [
    "PROMPT_PATH",
    "PROMPT_VERSION",
    "generated_examples",
    "generated_vocabulary",
    "load_prompt",
]
