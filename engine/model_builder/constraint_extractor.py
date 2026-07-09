from __future__ import annotations

from engine.models import CanonicalProblem
from .model_types import PhysicalBody, PhysicalConstraint


def _c(out: list[PhysicalConstraint], kind: str, description: str, *, equation: str | None = None, bodies: list[str] | None = None, source: str | None = None, notes: list[str] | None = None):
    out.append(PhysicalConstraint(
        id=f'{kind}_{len(out)+1}',
        kind=kind,
        description=description,
        equation=equation,
        related_bodies=bodies or [],
        source=source,
        notes=notes or [],
    ))


def build_constraints(c: CanonicalProblem, bodies: list[PhysicalBody]) -> list[PhysicalConstraint]:
    constraints: list[PhysicalConstraint] = []
    st = c.system_type

    if st in {'pulley_table_hanging', 'pulley_atwood', 'pulley_incline_hanging'}:
        _c(constraints, 'massless_string', '줄은 질량이 없고 늘어나지 않습니다.', bodies=['body_1', 'body_2'], source='idealization')
        _c(constraints, 'same_acceleration_magnitude', '같은 줄에 연결되어 두 물체의 가속도 크기가 같습니다.', equation='|a1|=|a2|=a', bodies=['body_1', 'body_2'], source='string_constraint')
        _c(constraints, 'massless_frictionless_pulley', '질량 없는 도르래에서는 줄 양쪽 장력이 같습니다.', equation='T_left=T_right=T', source='pulley_constraint')
        if c.friction_type == 'static':
            _c(constraints, 'static_friction_inequality', '정지마찰은 먼저 버틸 수 있는지 부등식으로 판정합니다.', equation='|f_s| <= mu_s*N', bodies=['body_1'], source='contact')
    elif st == 'massive_pulley_atwood':
        _c(constraints, 'massless_string', '줄은 질량이 없고 미끄러지지 않습니다.', bodies=['body_1', 'body_2', 'pulley'], source='idealization')
        _c(constraints, 'no_slip_pulley', '줄과 도르래가 미끄러지지 않아 선가속도와 각가속도가 연결됩니다.', equation='a=alpha*R', bodies=['pulley'], source='rolling_constraint')
        _c(constraints, 'pulley_rotation', '도르래 회전방정식이 필요하므로 양쪽 장력이 달라질 수 있습니다.', equation='(T2-T1)R=I alpha', bodies=['pulley'], source='newton_euler')
    elif st == 'particle_on_incline':
        _c(constraints, 'contact_normal', '경사면을 뚫고 움직이지 않으므로 법선방향 가속도는 0입니다.', equation='sum F_normal=0', bodies=['body'], source='contact')
        if c.subtype == 'no_friction':
            _c(constraints, 'frictionless_contact', '마찰을 무시합니다.', equation='f=0', bodies=['body'], source='problem_statement')
        elif c.subtype == 'with_friction':
            if c.friction_type == 'static':
                _c(constraints, 'static_friction_inequality', '정지마찰 문제는 먼저 움직이는지 판정합니다.', equation='mg*sin(theta) <= mu_s*mg*cos(theta)', bodies=['body'], source='contact')
            _c(constraints, 'friction_model', '마찰력은 운동/운동경향 반대방향이며 계수와 수직항력으로 결정됩니다.', equation='f=mu*N', bodies=['body'], source='contact')
    elif st in {'pure_rolling_energy', 'rolling_energy_general'}:
        _c(constraints, 'pure_rolling', '미끄러지지 않는 구름 조건입니다.', equation='v=omega*R', bodies=['body'], source='kinematic_constraint')
        _c(constraints, 'static_friction_no_work', '이상적 순수 구름에서 접점 정지마찰은 에너지식에서 일을 하지 않습니다.', bodies=['body'], source='energy_model')
    elif st == 'projectile_motion':
        _c(constraints, 'no_air_resistance', '공기저항을 무시합니다.', equation='a_x=0, a_y=-g', bodies=['body'], source='idealization')
    elif st == 'constant_force_work':
        _c(constraints, 'constant_force', '힘은 이동 구간 동안 일정하다고 봅니다.', equation='W=F*s*cos(theta)', bodies=['body'], source='work_definition')
    elif 'rigid_body' in st:
        _c(constraints, 'rigid_distance', '강체 내부 두 점 사이의 상대 위치벡터 r_B/A는 고정됩니다.', equation='v_B=v_A+omega×r_B/A', bodies=['rigid_body'], source='rigid_body_kinematics')
        if 'acceleration' in st:
            _c(constraints, 'rigid_acceleration_relation', '평면강체 가속도 관계를 사용합니다.', equation='a_B=a_A+alpha×r+omega×(omega×r)', bodies=['rigid_body'], source='rigid_body_kinematics')
    elif st == 'collision_1d':
        _c(constraints, 'linear_momentum', '외부 충격량을 무시하면 충돌선 방향 운동량이 보존됩니다.', equation='m1v1+m2v2=m1v1f+m2v2f', bodies=['body_1', 'body_2'], source='momentum')
        if c.flags.get('perfectly_inelastic'):
            _c(constraints, 'common_final_velocity', '완전비탄성 충돌에서는 충돌 후 두 물체가 함께 움직입니다.', equation='v1f=v2f', bodies=['body_1', 'body_2'], source='collision_model')
        elif 'e' in c.knowns or c.flags.get('elastic'):
            _c(constraints, 'restitution', '반발계수 식을 함께 사용합니다.', equation='e=-(v2f-v1f)/(v2-v1)', bodies=['body_1', 'body_2'], source='collision_model')

    return constraints
