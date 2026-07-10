from __future__ import annotations

from engine.models import CanonicalProblem, Quantity
from .model_types import PhysicalBody


def _mass(c: CanonicalProblem, key: str) -> Quantity | None:
    return c.knowns.get(key)


def _body_from_quantity(body_id: str, name: str, role: str, q: Quantity | None, *, shape: str | None = None, surface: str | None = None, state: str | None = None, notes: list[str] | None = None) -> PhysicalBody:
    return PhysicalBody(
        id=body_id,
        name=name,
        role=role,
        mass_symbol=q.symbol if q else None,
        mass_value=q.value if q else None,
        mass_unit=q.unit if q else None,
        shape=shape,
        surface=surface,
        state=state,
        notes=notes or [],
    )


def build_bodies(c: CanonicalProblem) -> list[PhysicalBody]:
    bodies: list[PhysicalBody] = []
    st = c.system_type

    if st == 'pulley_table_hanging':
        bodies.append(_body_from_quantity('body_1', '수평면 위 물체', 'block_on_table', _mass(c, 'm1'), surface='horizontal_table'))
        bodies.append(_body_from_quantity('body_2', '매달린 물체', 'hanging_mass', _mass(c, 'm2'), surface='vertical_hanging'))
    elif st == 'pulley_atwood':
        bodies.append(_body_from_quantity('body_1', '왼쪽/1번 매달린 물체', 'hanging_mass_left', _mass(c, 'm1'), surface='vertical_hanging'))
        bodies.append(_body_from_quantity('body_2', '오른쪽/2번 매달린 물체', 'hanging_mass_right', _mass(c, 'm2'), surface='vertical_hanging'))
    elif st == 'pulley_incline_hanging':
        bodies.append(_body_from_quantity('body_1', '경사면 위 물체', 'block_on_incline', _mass(c, 'm1'), surface='incline'))
        bodies.append(_body_from_quantity('body_2', '매달린 물체', 'hanging_mass', _mass(c, 'm2'), surface='vertical_hanging'))
    elif st == 'massive_pulley_atwood':
        bodies.append(_body_from_quantity('body_1', '1번 매달린 물체', 'hanging_mass_left', _mass(c, 'm1'), surface='vertical_hanging'))
        bodies.append(_body_from_quantity('body_2', '2번 매달린 물체', 'hanging_mass_right', _mass(c, 'm2'), surface='vertical_hanging'))
        bodies.append(PhysicalBody(id='pulley', name='질량/관성 있는 도르래', role='rotating_pulley', shape='pulley', notes=['I와 R로 회전 방정식 생성']))
    elif st == 'single_particle_newton':
        bodies.append(_body_from_quantity('body', '물체', 'single_particle', _mass(c, 'm'), state='accelerating'))
    elif st == 'particle_on_incline':
        bodies.append(_body_from_quantity('body', '경사면 위 블록', 'block_on_incline', _mass(c, 'm'), surface='incline'))
    elif st in {'pure_rolling_energy', 'rolling_energy_general'}:
        bodies.append(_body_from_quantity('body', '구름 강체', 'rolling_body', _mass(c, 'm'), shape=c.body_shape, surface='incline_or_height_drop', state='pure_rolling'))
    elif st == 'projectile_motion':
        bodies.append(_body_from_quantity('body', '투사체', 'projectile_particle', _mass(c, 'm'), state='free_flight'))
    elif st == 'constant_force_work':
        bodies.append(_body_from_quantity('body', '외력을 받는 물체', 'particle_or_block', _mass(c, 'm'), state='translated'))
    elif 'rigid_body' in st:
        bodies.append(PhysicalBody(id='rigid_body', name='평면 강체', role='planar_rigid_body', shape='rigid_body', notes=['점 A/B 관계를 벡터로 모델링']))
    elif 'spring' in st:
        bodies.append(_body_from_quantity('body', '스프링-질량계 물체', 'spring_mass', _mass(c, 'm'), state='oscillating_or_released'))
    elif st == 'collision_1d':
        bodies.append(_body_from_quantity('body_1', '충돌 물체 1', 'colliding_particle', _mass(c, 'm1')))
        bodies.append(_body_from_quantity('body_2', '충돌 물체 2', 'colliding_particle', _mass(c, 'm2')))
    elif c.objects:
        for i, obj in enumerate(c.objects, start=1):
            q = None
            if obj.get('name') == 'object_1':
                q = _mass(c, 'm1')
            elif obj.get('name') == 'object_2':
                q = _mass(c, 'm2')
            elif obj.get('name') == 'body':
                q = _mass(c, 'm')
            bodies.append(_body_from_quantity(f'body_{i}', obj.get('name', f'body_{i}'), 'unknown_body', q))
    else:
        bodies.append(_body_from_quantity('body', '해석 대상 물체', 'unknown_body', _mass(c, 'm')))

    return bodies
