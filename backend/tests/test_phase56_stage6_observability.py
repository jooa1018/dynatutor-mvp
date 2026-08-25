import pytest

from engine.mechanics.multimodal_observability import (
    audit_metric_payload,
    build_multimodal_metric_event,
)


def test_metric_payload_has_only_low_cardinality_counts_and_terminal() -> None:
    event = build_multimodal_metric_event(
        terminal="confirmation_required",
        image_count=2,
        observation_count=5,
        conflict_count=1,
        confirmation_count=0,
    )
    payload = event.as_dict()
    assert audit_metric_payload(payload)
    assert set(payload) == {
        "terminal",
        "image_count",
        "observation_count",
        "conflict_count",
        "confirmation_count",
    }


def test_metric_builder_rejects_negative_or_non_integer_counts() -> None:
    with pytest.raises(ValueError):
        build_multimodal_metric_event(
            terminal="ready",
            image_count=-1,
            observation_count=0,
            conflict_count=0,
            confirmation_count=0,
        )
