from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from engine.textbook_parser.contracts import AssumptionKind, AssumptionProposal, TextbookProblemParseV1


ASSUMPTION_POLICY_VERSION = "assumption-policy-v1"


class AssumptionDisposition(str, Enum):
    accepted_default = "accepted_default"
    accepted_visible = "accepted_visible"
    needs_confirmation = "needs_confirmation"
    rejected = "rejected"


@dataclass(frozen=True)
class AssumptionEvaluation:
    assumption_id: str
    disposition: AssumptionDisposition
    reason_code: str
    user_visible: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "assumption_id": self.assumption_id,
            "disposition": self.disposition.value,
            "reason_code": self.reason_code,
            "user_visible": self.user_visible,
        }


def evaluate_assumption(problem_text: str, proposal: AssumptionProposal) -> AssumptionEvaluation:
    support = proposal.supporting_quote or ""
    context = support or problem_text
    compact = re.sub(r"\s+", "", context.lower())
    kind = proposal.kind

    if kind == AssumptionKind.starts_from_rest:
        explicit_rest = any(token in compact for token in ("정지상태", "가만히", "startsfromrest"))
        race_start = bool(re.search(r"(?:경주|race).*(?:처음|출발)|(?:처음|출발).*(?:경주|race)", compact))
        if explicit_rest or race_start:
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "supported_start_rest_context",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "start_rest_not_explicit",
            True,
        )
    if kind == AssumptionKind.ends_at_rest:
        if any(token in compact for token in ("정지", "멈출", "comestorest")):
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "supported_end_rest_context",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "end_rest_not_explicit",
            True,
        )
    if kind == AssumptionKind.constant_gravity:
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.accepted_default,
            "standard_near_earth_gravity",
            False,
        )
    if kind == AssumptionKind.no_air_resistance:
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.accepted_visible,
            "ideal_projectile_assumption_visible",
            True,
        )
    if kind == AssumptionKind.frictionless:
        if any(token in compact for token in ("마찰없", "마찰을무시", "frictionless")):
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "explicit_frictionless_language",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "friction_state_not_stated",
            True,
        )
    if kind in {AssumptionKind.massless_rope, AssumptionKind.massless_pulley, AssumptionKind.inextensible_rope}:
        if any(token in compact for token in ("가벼운", "질량을무시", "늘어나지", "massless", "inextensible")):
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "ideal_constraint_explicit_language",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "ideal_constraint_not_stated",
            True,
        )
    if kind == AssumptionKind.pure_rolling:
        if any(token in compact for token in ("미끄러지지", "순수구름", "withoutslipping")):
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "no_slip_explicit_language",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "rolling_does_not_imply_no_slip",
            True,
        )
    if kind == AssumptionKind.fixed_point:
        if any(token in compact for token in ("고정점", "고정되어", "fixed")):
            return AssumptionEvaluation(
                proposal.assumption_id,
                AssumptionDisposition.accepted_visible,
                "fixed_point_explicit_language",
                True,
            )
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "fixed_point_not_stated",
            True,
        )
    if kind == AssumptionKind.direction_choice:
        return AssumptionEvaluation(
            proposal.assumption_id,
            AssumptionDisposition.needs_confirmation,
            "direction_choice_requires_user",
            True,
        )
    return AssumptionEvaluation(
        proposal.assumption_id,
        AssumptionDisposition.rejected,
        "unsupported_assumption_kind",
        True,
    )


def evaluate_assumptions(problem_text: str, parse: TextbookProblemParseV1) -> tuple[AssumptionEvaluation, ...]:
    return tuple(evaluate_assumption(problem_text, item) for item in parse.assumption_proposals)


__all__ = [
    "ASSUMPTION_POLICY_VERSION",
    "AssumptionDisposition",
    "AssumptionEvaluation",
    "evaluate_assumption",
    "evaluate_assumptions",
]
