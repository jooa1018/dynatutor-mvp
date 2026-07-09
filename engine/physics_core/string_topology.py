from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StringNode:
    id: str
    body_id: str
    coordinate: str
    positive_direction: str


@dataclass
class PulleyTopology:
    kind: str
    nodes: list[StringNode] = field(default_factory=list)
    tension_symbols: list[str] = field(default_factory=list)
    acceleration_constraints: list[str] = field(default_factory=list)
    tension_constraints: list[str] = field(default_factory=list)
    rotation_constraints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "nodes": [n.__dict__ for n in self.nodes],
            "tension_symbols": self.tension_symbols,
            "acceleration_constraints": self.acceleration_constraints,
            "tension_constraints": self.tension_constraints,
            "rotation_constraints": self.rotation_constraints,
            "notes": self.notes,
        }


def topology_for_system(system_type: str) -> PulleyTopology | None:
    if system_type == "pulley_atwood":
        return PulleyTopology(
            kind="fixed_massless_atwood",
            nodes=[
                StringNode("left_segment", "body_1", "y", "up"),
                StringNode("right_segment", "body_2", "y", "down"),
            ],
            tension_symbols=["T"],
            acceleration_constraints=["a_body1_up = a_body2_down = a"],
            tension_constraints=["T_left = T_right = T"],
            notes=["고정된 질량 없는 도르래에서는 양쪽 장력이 같습니다."],
        )
    if system_type == "pulley_table_hanging":
        return PulleyTopology(
            kind="fixed_massless_table_hanging",
            nodes=[
                StringNode("table_segment", "body_1", "x", "right"),
                StringNode("vertical_segment", "body_2", "y", "down"),
            ],
            tension_symbols=["T"],
            acceleration_constraints=["a_body1_right = a_body2_down = a"],
            tension_constraints=["T_table = T_vertical = T"],
            notes=["줄 길이 제약 때문에 수평 물체와 매달린 물체의 가속도 크기가 같습니다."],
        )
    if system_type == "pulley_incline_hanging":
        return PulleyTopology(
            kind="fixed_massless_incline_hanging",
            nodes=[
                StringNode("incline_segment", "body_1", "x", "up_slope"),
                StringNode("vertical_segment", "body_2", "y", "down"),
            ],
            tension_symbols=["T"],
            acceleration_constraints=["a_body1_up_slope = a_body2_down = a"],
            tension_constraints=["T_incline = T_vertical = T"],
            notes=["m2가 내려가면 m1은 경사면 위로 올라가는 방향을 +로 잡습니다."],
        )
    if system_type == "massive_pulley_atwood":
        return PulleyTopology(
            kind="fixed_massive_atwood",
            nodes=[
                StringNode("left_segment", "body_1", "y", "up"),
                StringNode("right_segment", "body_2", "y", "down"),
                StringNode("pulley_rim", "pulley", "rotation", "m2_down_positive"),
            ],
            tension_symbols=["T1", "T2"],
            acceleration_constraints=["a_body1_up = a_body2_down = a"],
            tension_constraints=["T1 != T2 generally"],
            rotation_constraints=["a = alpha*R", "(T2-T1)R = I alpha"],
            notes=["도르래 관성모멘트가 있으면 양쪽 장력이 달라질 수 있습니다."],
        )
    return None
