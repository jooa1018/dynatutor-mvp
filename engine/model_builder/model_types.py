from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PhysicalBody:
    id: str
    name: str
    role: str
    mass_symbol: str | None = None
    mass_value: float | None = None
    mass_unit: str | None = None
    shape: str | None = None
    surface: str | None = None
    state: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class PhysicalForce:
    id: str
    body_id: str
    kind: str
    symbol: str
    direction: str
    axis: str | None = None
    magnitude_expr: str | None = None
    constitutive_equation: str | None = None
    source: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class PhysicalConstraint:
    id: str
    kind: str
    description: str
    equation: str | None = None
    related_bodies: list[str] = field(default_factory=list)
    source: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class CoordinateFrame:
    id: str = 'model_frame'
    positive_directions: dict[str, str] = field(default_factory=dict)
    body_axes: dict[str, dict[str, str]] = field(default_factory=dict)
    angular_positive: str | None = None
    notes: list[str] = field(default_factory=list)



@dataclass
class GeneratedEquation:
    id: str
    kind: str
    body_id: str | None
    axis: str | None
    equation: str
    sympy_repr: str | None = None
    source_forces: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class GeneratedEquationSystem:
    generator: str
    equations: list[GeneratedEquation] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    substitutions: dict[str, float] = field(default_factory=dict)
    equations_ready: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PhysicalModel:
    system_type: str
    subtype: str | None = None
    bodies: list[PhysicalBody] = field(default_factory=list)
    forces: list[PhysicalForce] = field(default_factory=list)
    constraints: list[PhysicalConstraint] = field(default_factory=list)
    coordinates: CoordinateFrame = field(default_factory=CoordinateFrame)
    assumptions: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    equations_ready: bool = False
    model_confidence: str = '보통'
    model_notes: list[str] = field(default_factory=list)
    generated_equation_system: GeneratedEquationSystem | None = None
    generated_energy_momentum_system: GeneratedEquationSystem | None = None
    friction_decisions: list[dict[str, Any]] = field(default_factory=list)
    string_topology: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.bodies:
            lines.append('물체: ' + ', '.join(f'{b.id}({b.role})' for b in self.bodies))
        if self.forces:
            by_body: dict[str, list[str]] = {}
            for f in self.forces:
                by_body.setdefault(f.body_id, []).append(f'{f.symbol}:{f.direction}')
            lines.extend(f'{body} 힘: ' + ', '.join(items) for body, items in by_body.items())
        if self.constraints:
            lines.append('제약조건: ' + ', '.join(c.kind for c in self.constraints))
        lines.append('방정식 생성 준비: ' + ('가능' if self.equations_ready else '추가 조건 필요'))
        if self.generated_equation_system and self.generated_equation_system.equations:
            lines.append('생성 방정식: ' + ', '.join(eq.equation for eq in self.generated_equation_system.equations[:4]))
        if self.generated_energy_momentum_system and self.generated_energy_momentum_system.equations:
            lines.append('에너지/운동량 식: ' + ', '.join(eq.equation for eq in self.generated_energy_momentum_system.equations[:4]))
        if self.friction_decisions:
            lines.append('마찰 판정: ' + ', '.join(d.get('status', 'unknown') for d in self.friction_decisions))
        if self.string_topology:
            lines.append('줄/도르래 topology: ' + self.string_topology.get('kind', 'unknown'))
        return lines
