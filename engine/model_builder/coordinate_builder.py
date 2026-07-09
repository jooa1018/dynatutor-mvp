from __future__ import annotations

from engine.models import CanonicalProblem
from .model_types import CoordinateFrame, PhysicalBody


def build_coordinates(c: CanonicalProblem, bodies: list[PhysicalBody]) -> CoordinateFrame:
    frame = CoordinateFrame()
    st = c.system_type
    frame.angular_positive = 'counterclockwise_positive'

    if st == 'particle_on_incline':
        frame.positive_directions = {'x': '경사면 아래쪽', 'y': '경사면 바깥쪽'}
        frame.body_axes['body'] = {'x': 'down_slope', 'y': 'normal_out'}
    elif st == 'pulley_table_hanging':
        frame.positive_directions = {'body_1.x': '수평면 오른쪽', 'body_2.y': '아래쪽'}
        frame.body_axes['body_1'] = {'x': 'right_along_table', 'y': 'up'}
        frame.body_axes['body_2'] = {'y': 'down'}
    elif st == 'pulley_atwood':
        frame.positive_directions = {'body_1.y': '위쪽', 'body_2.y': '아래쪽'}
        frame.body_axes['body_1'] = {'y': 'up_assumed'}
        frame.body_axes['body_2'] = {'y': 'down_assumed'}
        frame.notes.append('Atwood solver는 m2 하강을 +로 가정하고 부호로 실제 방향을 판정합니다.')
    elif st == 'pulley_incline_hanging':
        frame.positive_directions = {'body_1.x': '경사면 위쪽', 'body_2.y': '아래쪽'}
        frame.body_axes['body_1'] = {'x': 'up_slope', 'y': 'normal_out'}
        frame.body_axes['body_2'] = {'y': 'down'}
    elif st == 'massive_pulley_atwood':
        frame.positive_directions = {'body_1.y': '위쪽', 'body_2.y': '아래쪽', 'pulley.alpha': 'm2 하강에 대응하는 회전방향'}
        frame.body_axes['body_1'] = {'y': 'up_assumed'}
        frame.body_axes['body_2'] = {'y': 'down_assumed'}
    elif st in {'pure_rolling_energy', 'rolling_energy_general'}:
        frame.positive_directions = {'x': '구름 진행방향', 'rotation': 'v=omega*R와 일치하는 회전방향'}
        frame.body_axes['body'] = {'x': 'path_tangent', 'y': 'normal'}
    elif st == 'projectile_motion':
        frame.positive_directions = {'x': '수평 오른쪽', 'y': '위쪽'}
        frame.body_axes['body'] = {'x': 'right', 'y': 'up'}
    elif st == 'constant_force_work':
        frame.positive_directions = {'s': '변위 방향'}
        frame.body_axes['body'] = {'s': 'displacement_direction'}
    elif 'rigid_body' in st:
        angular = '반시계방향(+)' if c.coordinate_data.get('angular_sign', 1) >= 0 else '시계방향(-)'
        frame.positive_directions = {'x': '오른쪽', 'y': '위쪽', 'omega': angular}
        frame.body_axes['rigid_body'] = {'r_B/A': '문제의 좌표/방향 표현 사용'}
        if 'rBAx' in c.coordinate_data and 'rBAy' in c.coordinate_data:
            frame.notes.append(f"r_B/A=({c.coordinate_data['rBAx']:.3g}, {c.coordinate_data['rBAy']:.3g}) m")
        if 'vAx' in c.coordinate_data or 'vAy' in c.coordinate_data:
            frame.notes.append(f"v_A=({c.coordinate_data.get('vAx', 0):.3g}, {c.coordinate_data.get('vAy', 0):.3g}) m/s")
        if c.coordinate_data.get('parse_notes'):
            frame.notes.extend(c.coordinate_data.get('parse_notes', []))
    else:
        frame.positive_directions = {'x': '문제에서 정한 양의 방향'}
        frame.notes.append('일반 좌표계입니다. solver별 StepCard에서 구체화됩니다.')

    return frame
