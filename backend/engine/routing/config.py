from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingConfig:
    minimum_selection_score: float = 0.55
    selection_margin: float = 0.08
    cross_family_margin: float = 0.16
    missing_requirement_penalty: float = 0.15
    output_contradiction_penalty: float = 0.20
    evidence_candidate_base: float = 0.55
    evidence_candidate_step: float = 0.05
    evidence_candidate_ceiling: float = 0.75


ROUTING_CONFIG = RoutingConfig()
