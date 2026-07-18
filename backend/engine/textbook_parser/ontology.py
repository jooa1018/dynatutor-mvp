from __future__ import annotations

from types import MappingProxyType


ONTOLOGY_VERSION = "textbook-ontology-v2"

SEMANTIC_TO_CANONICAL_SYMBOL = MappingProxyType(
    {
        "acceleration": "a",
        "angular_acceleration": "alpha",
        "angular_velocity": "omega",
        "coefficient_of_friction": "mu",
        "displacement": "s",
        "distance": "s",
        "duration": "t",
        "final_velocity": "vf",
        "force": "F",
        "height": "h",
        "initial_velocity": "v0",
        "mass": "m",
        "mass_1": "m1",
        "mass_2": "m2",
        "moment_of_inertia": "I",
        "radius": "R",
        "restitution_coefficient": "e",
        "spring_constant": "k",
        "time": "t",
        "torque": "tau",
        "velocity": "v",
        "velocity_before": "v",
        "velocity_after": "v",
        "work": "W",
    }
)


def canonical_symbol(semantic_key: str) -> str | None:
    return SEMANTIC_TO_CANONICAL_SYMBOL.get(semantic_key)


__all__ = ["ONTOLOGY_VERSION", "SEMANTIC_TO_CANONICAL_SYMBOL", "canonical_symbol"]
