from __future__ import annotations

from engine.models import CanonicalProblem
from .model_types import PhysicalBody, PhysicalForce


def _add(force_list: list[PhysicalForce], body_id: str, kind: str, symbol: str, direction: str, *, axis: str | None = None, magnitude_expr: str | None = None, constitutive_equation: str | None = None, source: str | None = None, notes: list[str] | None = None):
    force_list.append(PhysicalForce(
        id=f'{body_id}_{kind}_{len(force_list)+1}',
        body_id=body_id,
        kind=kind,
        symbol=symbol,
        direction=direction,
        axis=axis,
        magnitude_expr=magnitude_expr,
        constitutive_equation=constitutive_equation,
        source=source,
        notes=notes or [],
    ))


def build_forces(c: CanonicalProblem, bodies: list[PhysicalBody]) -> list[PhysicalForce]:
    forces: list[PhysicalForce] = []
    st = c.system_type

    if st == 'single_particle_newton':
        _add(forces, 'body', 'net_force', 'F_net', '+x', axis='x', magnitude_expr='F', source='given_net_force', notes=['단일 질점 F=ma 문제의 알짜힘입니다.'])
    elif st == 'particle_on_incline':
        _add(forces, 'body', 'weight_component_parallel', 'mg sinθ', '경사면 아래쪽', axis='x', magnitude_expr='m*g*sin(theta)', source='gravity')
        _add(forces, 'body', 'weight_component_normal', 'mg cosθ', '경사면 안쪽', axis='y', magnitude_expr='m*g*cos(theta)', source='gravity')
        _add(forces, 'body', 'normal', 'N', '경사면 바깥쪽', axis='y', magnitude_expr='N', source='contact')
        if c.subtype == 'with_friction' or c.flags.get('friction'):
            _add(forces, 'body', 'friction', 'f', '운동/운동경향 반대', axis='x', constitutive_equation='f=mu*N', source='contact')
    elif st == 'pulley_table_hanging':
        _add(forces, 'body_1', 'weight', 'm1g', '아래쪽', axis='y', magnitude_expr='m1*g', source='gravity')
        _add(forces, 'body_1', 'normal', 'N1', '위쪽', axis='y', magnitude_expr='N1', source='contact')
        _add(forces, 'body_1', 'tension', 'T', '수평면 오른쪽', axis='x', magnitude_expr='T', source='string')
        if c.friction_type and c.friction_type != 'none':
            _add(forces, 'body_1', 'friction', 'f', '수평 운동경향 반대', axis='x', constitutive_equation='f=mu*N1', source='contact')
        _add(forces, 'body_2', 'weight', 'm2g', '아래쪽', axis='y', magnitude_expr='m2*g', source='gravity')
        _add(forces, 'body_2', 'tension', 'T', '위쪽', axis='y', magnitude_expr='T', source='string')
    elif st == 'pulley_atwood':
        _add(forces, 'body_1', 'weight', 'm1g', '아래쪽', axis='y', magnitude_expr='m1*g', source='gravity')
        _add(forces, 'body_1', 'tension', 'T', '위쪽', axis='y', magnitude_expr='T', source='string')
        _add(forces, 'body_2', 'weight', 'm2g', '아래쪽', axis='y', magnitude_expr='m2*g', source='gravity')
        _add(forces, 'body_2', 'tension', 'T', '위쪽', axis='y', magnitude_expr='T', source='string')
    elif st == 'pulley_incline_hanging':
        _add(forces, 'body_1', 'weight_parallel', 'm1g sinθ', '경사면 아래쪽', axis='x', magnitude_expr='m1*g*sin(theta)', source='gravity')
        _add(forces, 'body_1', 'weight_normal', 'm1g cosθ', '경사면 안쪽', axis='y', magnitude_expr='m1*g*cos(theta)', source='gravity')
        _add(forces, 'body_1', 'normal', 'N1', '경사면 바깥쪽', axis='y', magnitude_expr='N1', source='contact')
        _add(forces, 'body_1', 'tension', 'T', '경사면 위쪽', axis='x', magnitude_expr='T', source='string')
        if c.friction_type and c.friction_type != 'none':
            _add(forces, 'body_1', 'friction', 'f', '운동/운동경향 반대', axis='x', constitutive_equation='f=mu*N1', source='contact')
        _add(forces, 'body_2', 'weight', 'm2g', '아래쪽', axis='y', magnitude_expr='m2*g', source='gravity')
        _add(forces, 'body_2', 'tension', 'T', '위쪽', axis='y', magnitude_expr='T', source='string')
    elif st == 'massive_pulley_atwood':
        _add(forces, 'body_1', 'weight', 'm1g', '아래쪽', axis='y', magnitude_expr='m1*g', source='gravity')
        _add(forces, 'body_1', 'tension', 'T1', '위쪽', axis='y', magnitude_expr='T1', source='string')
        _add(forces, 'body_2', 'weight', 'm2g', '아래쪽', axis='y', magnitude_expr='m2*g', source='gravity')
        _add(forces, 'body_2', 'tension', 'T2', '위쪽', axis='y', magnitude_expr='T2', source='string')
        _add(forces, 'pulley', 'torque_from_tensions', '(T2-T1)R', '회전방향', axis='rotation', magnitude_expr='(T2-T1)*R', source='string')
    elif st in {'pure_rolling_energy', 'rolling_energy_general'}:
        _add(forces, 'body', 'weight', 'mg', '아래쪽', magnitude_expr='m*g', source='gravity')
        _add(forces, 'body', 'normal', 'N', '접촉면 바깥쪽', source='contact')
        _add(forces, 'body', 'static_friction', 'f_s', '순수 구름을 만족시키는 접선방향', constitutive_equation='static, no work in ideal rolling', source='contact')
    elif st == 'projectile_motion':
        _add(forces, 'body', 'weight', 'mg', '아래쪽', axis='y', magnitude_expr='m*g', source='gravity')
        if not c.flags.get('air_resistance'):
            # no force object for air; assumption/constraint records it.
            pass
    elif st == 'constant_force_work':
        angle = c.force_direction or 'angle_required'
        _add(forces, 'body', 'applied_force', 'F', f'변위 방향 기준 {angle}', axis='s', magnitude_expr='F', source='external_agent', constitutive_equation='W=F*s*cos(theta)')
    elif 'spring' in st:
        _add(forces, 'body', 'spring_force', 'kx', '평형점 방향', magnitude_expr='k*x', source='spring', constitutive_equation='F_s=-kx')
    elif st == 'collision_1d':
        _add(forces, 'body_1', 'impulsive_contact', 'J', '충돌선 방향', axis='x', source='contact')
        _add(forces, 'body_2', 'impulsive_contact', '-J', '충돌선 반대방향', axis='x', source='contact')
    elif 'rigid_body' in st:
        _add(forces, 'rigid_body', 'kinematic_relation', 'ω, α, r_B/A', '평면강체 운동학 관계', source='rigid_body_constraint', notes=['실제 힘이 아니라 속도/가속도 관계 모델 항목입니다.'])

    return forces
