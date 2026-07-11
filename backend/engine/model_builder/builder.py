from __future__ import annotations

from engine.models import CanonicalProblem, StepCard
from .coordinate_builder import build_coordinates
from .constraint_extractor import build_constraints
from .force_extractor import build_forces
from .model_types import PhysicalModel
from .object_extractor import build_bodies
from .friction_analyzer import build_friction_decisions
from engine.physics_core.string_topology import topology_for_system
# NOTE(Phase 33): equation_generators 는 model_builder.model_types 를 import 하므로
# 여기서 모듈 수준으로 역방향 import 를 하면 import 순서에 따라 순환이 터진다
# (registry 를 먼저 import 하면 ImportError). 사용 지점에서 지연 import 한다.


_SUPPORTED_MODEL_TYPES = {
    'particle_on_incline',
    'pulley_table_hanging',
    'pulley_atwood',
    'pulley_incline_hanging',
    'massive_pulley_atwood',
    'pure_rolling_energy',
    'rolling_energy_general',
    'projectile_motion',
    'constant_force_work',
    'plane_rigid_body_velocity',
    'plane_rigid_body_acceleration',
    'collision_1d',
    'spring_mass_vibration',
    'spring_energy',
    'spring_energy_speed',
}


def build_physical_model(c: CanonicalProblem) -> PhysicalModel:
    bodies = build_bodies(c)
    coordinates = build_coordinates(c, bodies)
    forces = build_forces(c, bodies)
    constraints = build_constraints(c, bodies)
    friction_decisions = build_friction_decisions(c)
    topology = topology_for_system(c.system_type)

    missing = list(c.missing_info)
    if c.system_type == 'ambiguous_pulley' and not any('도르래 구조' in x for x in missing):
        missing.append('도르래 구조: Atwood/table-hanging/incline-hanging/massive 중 하나')
    if c.system_type in {'pure_rolling_energy', 'rolling_energy_general'} and not c.body_shape and 'I' not in c.knowns:
        if not any('물체 종류' in x for x in missing):
            missing.append('물체 종류 또는 관성모멘트 I')

    equations_ready = c.system_type in _SUPPORTED_MODEL_TYPES and not missing
    confidence = '높음' if equations_ready and len(forces) + len(constraints) >= 3 else '보통' if c.system_type != 'unknown' else '낮음'

    notes: list[str] = []
    if c.system_type not in _SUPPORTED_MODEL_TYPES:
        notes.append('Phase 14 PhysicalModel Builder가 아직 이 유형의 방정식 생성 준비 여부를 보장하지 않습니다.')
    if equations_ready:
        notes.append('물체/힘/제약조건/좌표축이 solver에 넘길 수 있는 수준으로 구성되었습니다.')
    else:
        notes.append('추가 조건이 필요하거나 아직 모델 빌더 지원 범위 밖입니다.')

    model = PhysicalModel(
        system_type=c.system_type,
        subtype=c.subtype,
        bodies=bodies,
        forces=forces,
        constraints=constraints,
        coordinates=coordinates,
        assumptions=list(c.assumptions),
        missing_info=missing,
        equations_ready=equations_ready,
        model_confidence=confidence,
        model_notes=notes,
        friction_decisions=friction_decisions,
        string_topology=topology.to_dict() if topology else None,
    )
    # Phase 45: keep the legacy dataclass/API view stable while attaching an
    # internal typed model for the three declared vertical slices. Dynamic
    # attachment deliberately keeps PhysicalModel.to_dict() byte-for-byte
    # compatible with the pre-Phase-45 serialization contract.
    from .typed_builder import build_typed_dynamics_model

    model.typed_model = build_typed_dynamics_model(c, model)

    from engine.equation_generators.particle_newton import build_particle_newton_system
    from engine.equation_generators.energy_momentum import build_energy_momentum_system

    generated = build_particle_newton_system(c, model)
    if generated.equations:
        model.generated_equation_system = generated
        # equations_ready remains conservative: model + generated system must both be ready for Newton-supported types.
        if c.system_type in {'particle_on_incline', 'pulley_table_hanging', 'pulley_atwood', 'pulley_incline_hanging', 'massive_pulley_atwood'}:
            model.equations_ready = equations_ready and generated.equations_ready

    generated_em = build_energy_momentum_system(c, model)
    if generated_em.equations:
        model.generated_energy_momentum_system = generated_em
        if c.system_type in {'constant_force_work', 'work_energy_speed', 'spring_mass_vibration', 'spring_energy', 'spring_energy_speed', 'pure_rolling_energy', 'rolling_energy_general', 'impulse_momentum', 'collision_1d'}:
            model.equations_ready = equations_ready and generated_em.equations_ready
    return model


def physical_model_step_cards(model: PhysicalModel) -> list[StepCard]:
    body_line = ', '.join(f'{b.name}({b.role})' for b in model.bodies) or '물체 추출 없음'
    force_count = len(model.forces)
    constraint_line = ', '.join(c.kind for c in model.constraints) or '명시 제약조건 없음'
    coord_line = '; '.join(f'{k}: {v}' for k, v in model.coordinates.positive_directions.items()) or 'solver 기본 좌표계'
    cards = [
        StepCard('물리 모델: 물체 추출', body_line),
        StepCard('물리 모델: 힘/상호작용', f'{force_count}개의 힘/상호작용을 구성했습니다.'),
        StepCard('물리 모델: 제약조건', constraint_line),
        StepCard('물리 모델: 좌표축', coord_line),
    ]
    if model.string_topology:
        cards.append(StepCard('물리 모델: 줄/도르래 제약', model.string_topology.get('kind', 'unknown') + ' · ' + '; '.join(model.string_topology.get('acceleration_constraints', []))))
    if model.friction_decisions:
        lines = []
        for d in model.friction_decisions:
            lines.append(f"{d.get('mode')}: {d.get('equation_note')} → {d.get('status')}")
        cards.append(StepCard('물리 모델: 마찰 판정', '\n'.join(lines)))
    if model.generated_equation_system and model.generated_equation_system.equations:
        from engine.equation_generators.particle_newton import generated_equation_step_card

        cards.append(generated_equation_step_card(model.generated_equation_system))
    if model.generated_energy_momentum_system and model.generated_energy_momentum_system.equations:
        from engine.equation_generators.energy_momentum import generated_energy_momentum_step_card

        cards.append(generated_energy_momentum_step_card(model.generated_energy_momentum_system))
    return cards
