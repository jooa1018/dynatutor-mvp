"""One canonical reading of an exact spring natural-length endpoint.

The v2 corpus names the same physical boundary in two typed ways:
``reaches_natural_length`` and ``zero_spring_deformation``.  The engine stores
that boundary as ``zero_deformation``.  These spellings are equivalent only at
this explicit boundary; generic finish, inactive, relaxed text, force zero and
approximately-zero numbers are deliberately absent.

This module has no dependency on evaluator packages so the engine law remains
authoritative while corpus validation, projection and closure reuse its exact
predicate without an inverted engine-to-evaluator dependency.
"""

from __future__ import annotations

from typing import Any, Mapping


SPRING_ENDPOINT_CANONICAL_VERSION = (
    "phase56-stage7-spring-endpoint-canonical-v1"
)

ZERO_DEFORMATION = "zero_deformation"
_EXACT_SOURCE_ENDPOINTS: frozenset[str] = frozenset(
    {"reaches_natural_length", "zero_spring_deformation"}
)


def _token(value: Any) -> str | None:
    """Return one exact typed token, never a textual approximation."""

    if isinstance(value, Mapping):
        if "condition" in value:
            value = value["condition"]
        elif "state" in value:
            value = value["state"]
        else:
            return None
    value = getattr(value, "value", value)
    return value if type(value) is str else None


def canonical_spring_endpoint(value: Any) -> str | None:
    """Canonicalize only exact typed natural-length endpoint vocabulary."""

    token = _token(value)
    if token in _EXACT_SOURCE_ENDPOINTS or token == ZERO_DEFORMATION:
        return ZERO_DEFORMATION
    return None


def is_exact_zero_deformation_endpoint(value: Any) -> bool:
    """Whether ``value`` is the exact spring zero-deformation boundary."""

    return canonical_spring_endpoint(value) == ZERO_DEFORMATION


__all__ = [
    "SPRING_ENDPOINT_CANONICAL_VERSION",
    "ZERO_DEFORMATION",
    "canonical_spring_endpoint",
    "is_exact_zero_deformation_endpoint",
]
