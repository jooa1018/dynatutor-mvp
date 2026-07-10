from __future__ import annotations

from html import escape
from math import cos, radians, sin
from engine.models import CanonicalProblem


INK = "#1d2939"
MUTED = "#667085"
SURFACE = "#eef4ff"
BLUE = "#2f6df6"
GREEN = "#12b76a"
RED = "#b42318"
ORANGE = "#f79009"
PURPLE = "#7a5af8"
GRAY = "#98a2b3"


def _q(c: CanonicalProblem, key: str, default: float | None = None) -> float | None:
    item = c.knowns.get(key)
    if item and item.value is not None:
        return float(item.value)
    return default


def _svg_wrap(inner: str, height: int = 260, title: str = "free body diagram") -> str:
    """Wrap a schematic diagram in a deterministic SVG shell.

    Phase 7 intentionally keeps diagrams simple and inspectable: no canvas, no
    client-side drawing library, just SVG that can be returned from the API and
    rendered safely by the frontend.
    """
    return f"""<svg viewBox=\"0 0 560 {height}\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"{escape(title)}\">
  <defs>
    <marker id=\"arrowDark\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{INK}\" /></marker>
    <marker id=\"arrowBlue\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{BLUE}\" /></marker>
    <marker id=\"arrowGreen\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{GREEN}\" /></marker>
    <marker id=\"arrowRed\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{RED}\" /></marker>
    <marker id=\"arrowOrange\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{ORANGE}\" /></marker>
    <marker id=\"arrowPurple\" markerWidth=\"12\" markerHeight=\"12\" refX=\"10\" refY=\"4\" orient=\"auto\" markerUnits=\"strokeWidth\"><path d=\"M0,0 L0,8 L11,4 z\" fill=\"{PURPLE}\" /></marker>
    <filter id=\"softShadow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\"><feDropShadow dx=\"0\" dy=\"8\" stdDeviation=\"8\" flood-color=\"#101828\" flood-opacity=\"0.10\"/></filter>
    <style>
      .title {{ font: 800 17px ui-sans-serif, system-ui; fill:{INK}; }}
      .label {{ font: 800 14px ui-sans-serif, system-ui; }}
      .note {{ font: 700 12px ui-sans-serif, system-ui; fill:{MUTED}; }}
      .math {{ font: 800 13px ui-monospace, SFMono-Regular, Menlo, monospace; fill:{INK}; }}
      .thin {{ stroke-width:2; }}
      .force {{ stroke-width:3.4; stroke-linecap:round; marker-end:url(#arrowDark); }}
      .axis {{ stroke-width:2.4; stroke-linecap:round; stroke-dasharray:7 6; marker-end:url(#arrowDark); }}
      .surface {{ fill:{SURFACE}; stroke:{GRAY}; stroke-width:2.4; }}
      .body {{ fill:#fff; stroke:{BLUE}; stroke-width:3; filter:url(#softShadow); }}
    </style>
  </defs>
  <rect x=\"0\" y=\"0\" width=\"560\" height=\"{height}\" rx=\"24\" fill=\"#f8fafc\"/>
  {inner}
</svg>"""


def _text(x: float, y: float, label: str, color: str = INK, cls: str = "label", anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" class="{cls}" text-anchor="{anchor}">{escape(label)}</text>'


def _line(x1: float, y1: float, x2: float, y2: float, label: str = "", color: str = INK, marker: str = "arrowDark", width: float = 3.4, dash: str | None = None, label_dx: float = 8, label_dy: float = -8) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    midx, midy = (x1 + x2) / 2 + label_dx, (y1 + y2) / 2 + label_dy
    label_svg = _text(midx, midy, label, color) if label else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}" stroke-linecap="round" marker-end="url(#{marker})"{dash_attr}/>{label_svg}'


def _legend(items: list[tuple[str, str]], x: int = 378, y: int = 54) -> str:
    rows = [f'<rect x="{x-14}" y="{y-24}" width="166" height="{len(items)*24 + 24}" rx="14" fill="#fff" stroke="#e4e7ec"/>']
    rows.append(_text(x, y-4, "범례", INK, "label"))
    for i, (label, color) in enumerate(items):
        yy = y + 20 + i * 24
        rows.append(f'<line x1="{x}" y1="{yy}" x2="{x+22}" y2="{yy}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        rows.append(_text(x+31, yy+5, label, color, "note"))
    return "\n  ".join(rows)


def _angle_arc(cx: float, cy: float, r: float, start_deg: float, end_deg: float, label: str) -> str:
    sx = cx + r * cos(radians(start_deg))
    sy = cy - r * sin(radians(start_deg))
    ex = cx + r * cos(radians(end_deg))
    ey = cy - r * sin(radians(end_deg))
    large = 1 if abs(end_deg - start_deg) > 180 else 0
    lx = cx + (r + 14) * cos(radians((start_deg + end_deg) / 2))
    ly = cy - (r + 14) * sin(radians((start_deg + end_deg) / 2))
    return f'<path d="M {sx:.1f} {sy:.1f} A {r:.1f} {r:.1f} 0 {large} 0 {ex:.1f} {ey:.1f}" fill="none" stroke="{ORANGE}" stroke-width="2.4"/><text x="{lx:.1f}" y="{ly:.1f}" fill="{ORANGE}" class="label">{escape(label)}</text>'


def build_fbd_annotations(c: CanonicalProblem) -> list[str]:
    """Human-readable notes shown next to the diagram.

    The SVG teaches visually; these notes make the drawing's modeling choices
    explicit so a beginner does not mistake a schematic for a full CAD/FBD proof.
    """
    st = c.system_type
    if st == "particle_on_incline":
        notes = [
            "중력 mg는 항상 수직 아래 방향입니다. 경사면 아래 방향 성분은 mg sinθ입니다.",
            "수직항력 N은 경사면에 수직입니다. 좌표축도 경사면 방향/수직 방향으로 잡았습니다.",
        ]
        if c.subtype == "with_friction":
            notes.append("마찰력 f는 미끄러지는 경향과 반대 방향으로 그립니다. 아래로 미끄러지려는 기본 상황에서는 경사면 위쪽입니다.")
        else:
            notes.append("마찰 없음 조건이면 f=μN을 쓰지 않고, FBD에도 마찰력을 넣지 않습니다.")
        return notes
    if st == "pulley_table_hanging":
        return [
            "두 물체는 같은 줄에 연결되어 가속도 크기가 같습니다.",
            "수평 물체에는 장력 T가 줄 방향으로, 매달린 물체에는 m₂g와 T가 작용합니다.",
            "질량 없는 줄/마찰 없는 도르래 가정에서는 양쪽 장력 크기를 같게 둡니다.",
        ]
    if st == "vertical_circle":
        return [
            "중심 방향을 radial +로 잡으면 ΣF_radial = mv²/R입니다.",
            "최고점과 최저점은 중심 방향이 다르므로 장력/중력의 부호가 달라집니다.",
        ]
    if st == "pure_rolling_energy":
        return [
            "순수 구름에서는 접점이 순간적으로 정지하므로 v_G=ωR을 쓸 수 있습니다.",
            "에너지는 병진 운동에너지와 회전 운동에너지를 모두 포함해야 합니다.",
            "정지마찰은 이상적 순수 구름에서 보통 일을 하지 않습니다.",
        ]
    if st in {"spring_mass_vibration", "spring_energy"}:
        return [
            "스프링 힘은 변위 x와 반대 방향으로 작용합니다: F_s=-kx.",
            "진동 문제는 평형 위치를 기준으로 x축을 잡으면 식이 단순해집니다.",
        ]
    if st == "flat_curve_friction":
        return [
            "평평한 커브에서는 정지마찰이 중심 방향 구심력을 제공합니다.",
            "최대속도 조건은 f_s ≤ μ_s N의 한계에서 결정됩니다.",
        ]
    if st == "banked_curve_no_friction":
        return [
            "마찰 없는 뱅크 커브에서는 수직항력 N의 수평 성분이 구심력입니다.",
            "수직 성분은 중력 mg와 평형을 이룹니다.",
        ]
    if st == "polar_kinematics":
        return [
            "e_r은 원점에서 입자 쪽, e_θ는 θ가 증가하는 접선 방향입니다.",
            "가속도에는 -rθ_dot²와 2r_dotθ_dot 같은 회전 좌표계 항이 포함됩니다.",
        ]
    if st == "instant_center_velocity":
        return [
            "그 순간에는 IC를 중심으로 순수 회전처럼 보고 v=ωr을 씁니다.",
            "속도 방향은 IC와 점 P를 잇는 선에 수직입니다.",
        ]
    if st == "slot_pin_relative_motion":
        return [
            "핀의 절대속도는 슬롯 방향 상대속도 r_dot와 회전에 의한 접선속도 rω의 벡터합입니다.",
            "코리올리 항은 상대가속도를 다룰 때 2ωr_dot 방향으로 나타납니다.",
        ]
    if st == "plane_rigid_body_velocity":
        return [
            "강체의 두 점 속도는 v_B = v_A + ω×r_B/A로 연결됩니다.",
            "ω×r 성분은 A에서 B로 향하는 위치벡터에 수직입니다.",
        ]
    if st == "relative_acceleration_translation":
        return [
            "병진 기준계에서는 a_B = a_A + a_B/A로 더합니다.",
            "방향각이 주어진 문제는 반드시 x-y 성분으로 나눠 벡터합해야 합니다.",
        ]
    if st == "coriolis_relative_motion":
        return [
            "회전 기준계에서 상대속도가 있으면 코리올리 가속도 2ωv_rel이 생깁니다.",
            "코리올리 항은 상대속도 방향과 회전축 방향의 벡터곱으로 방향을 정합니다.",
        ]
    if st == "plane_rigid_body_acceleration":
        return [
            "αr은 접선 성분, ω²r은 법선 성분입니다.",
            "법선 성분은 B에서 기준점 A 쪽을 향합니다.",
        ]
    if st == "massive_pulley_atwood":
        return [
            "도르래 관성 때문에 양쪽 장력은 일반적으로 다릅니다: T1 ≠ T2.",
            "줄이 미끄러지지 않는다면 a=αR 구속조건을 씁니다.",
        ]
    if st == "rolling_energy_general":
        return [
            "주어진 관성모멘트 I를 사용해 병진+회전 에너지를 함께 계산합니다.",
            "미끄러지지 않을 때만 v_G=ωR 구속조건을 사용할 수 있습니다.",
        ]
    return ["이 도식은 개념도입니다. 실제 힘 크기와 길이는 문제 조건에 따라 달라집니다."]


def build_fbd_svg(c: CanonicalProblem) -> str | None:
    """Return a higher-quality, deterministic SVG for FBD guidance.

    It is still intentionally schematic. Phase 7 improves readability, axes,
    labels, color legend, and problem-specific direction hints.
    """
    st = c.system_type
    if st == "particle_on_incline":
        theta = _q(c, "theta", 30.0) or 30.0
        theta_label = f"θ≈{theta:g}°" if "theta" in c.knowns else "θ"
        friction = c.subtype == "with_friction"
        friction_svg = _line(258, 127, 194, 163, "f", RED, "arrowRed", label_dx=-18, label_dy=-6) if friction else ""
        friction_note = "마찰 있음: f는 미끄럼 경향 반대" if friction else "마찰 없음: f=μN 제외"
        inner = f"""
  {_text(24, 35, "경사면 위 블록 · 힘과 좌표축", INK, "title")}
  <polygon points="92,208 452,208 452,84" class="surface"/>
  <line x1="92" y1="208" x2="452" y2="208" stroke="{GRAY}" stroke-width="2"/>
  {_angle_arc(100, 208, 48, 0, 19, theta_label)}
  <g transform="translate(258 134) rotate(-19)"><rect x="-34" y="-23" width="68" height="46" rx="9" class="body"/></g>
  {_line(258,134,258,216,"mg", BLUE, "arrowBlue")}
  {_line(258,134,296,63,"N", GREEN, "arrowGreen")}
  {_line(258,134,332,172,"+x", INK, "arrowDark", 2.6, "7 6")}
  {_line(258,134,220,63,"+y", INK, "arrowDark", 2.6, "7 6", -36, -6)}
  {_line(258,134,306,160,"mg sinθ", ORANGE, "arrowOrange", 2.8, "5 5", 2, 22)}
  {_line(258,134,234,89,"mg cosθ", ORANGE, "arrowOrange", 2.8, "5 5", -74, -4)}
  {friction_svg}
  {_legend([("중력/성분", BLUE), ("수직항력", GREEN), ("마찰", RED if friction else GRAY), ("좌표축", INK)])}
  {_text(105, 238, friction_note, MUTED, "note")}
  {_text(105, 255, "개념도입니다. 화살표 길이는 실제 크기와 비례하지 않습니다.", MUTED, "note")}
"""
        return _svg_wrap(inner, 276, "incline free body diagram")

    if st == "pulley_table_hanging":
        inner = f"""
  {_text(24, 35, "수평면-도르래 · 두 물체 FBD", INK, "title")}
  <line x1="58" y1="159" x2="334" y2="159" stroke="{GRAY}" stroke-width="5" stroke-linecap="round"/>
  <rect x="116" y="103" width="78" height="56" rx="11" class="body"/>
  <circle cx="350" cy="98" r="31" fill="#fff" stroke="{BLUE}" stroke-width="3" filter="url(#softShadow)"/>
  <circle cx="350" cy="98" r="5" fill="{BLUE}"/>
  <path d="M194 131 L350 131 A33 33 0 0 0 383 98 L383 178" fill="none" stroke="{INK}" stroke-width="3"/>
  <rect x="348" y="178" width="70" height="50" rx="10" fill="#fff" stroke="{GREEN}" stroke-width="3" filter="url(#softShadow)"/>
  {_line(155,131,239,131,"T", GREEN, "arrowGreen")}
  {_line(155,131,155,83,"N₁", GREEN, "arrowGreen")}
  {_line(155,131,155,188,"m₁g", BLUE, "arrowBlue")}
  {_line(383,203,383,241,"m₂g", BLUE, "arrowBlue")}
  {_line(383,203,383,145,"T", GREEN, "arrowGreen")}
  {_line(158,183,236,183,"a", ORANGE, "arrowOrange", 2.8, "6 5")}
  {_line(433,203,433,242,"a", ORANGE, "arrowOrange", 2.8, "6 5")}
  {_legend([("중력", BLUE), ("장력/수직항력", GREEN), ("가속도", ORANGE)], 48, 55)}
  {_text(224, 248, "가정: 질량 없는 줄, 마찰 없는 도르래 → 양쪽 장력 T 동일", MUTED, "note")}
"""
        return _svg_wrap(inner, 268, "pulley free body diagram")

    if st == "vertical_circle":
        subtype = c.subtype or "top/bottom"
        if c.subtype == "bottom":
            px, py = 280, 190
            center_target = (280, 122)
            gravity_end = (280, 245)
            tension_end = (280, 118)
            pos_label = "최저점"
        else:
            px, py = 280, 54
            center_target = (280, 122)
            gravity_end = (280, 116)
            tension_end = (280, 116)
            pos_label = "최고점" if c.subtype == "top" else "지점"
        inner = f"""
  {_text(24, 35, f"수직 원운동 · {subtype}", INK, "title")}
  <circle cx="280" cy="122" r="68" fill="none" stroke="{GRAY}" stroke-width="3" stroke-dasharray="8 7"/>
  <circle cx="280" cy="122" r="5" fill="{INK}"/>
  <circle cx="{px}" cy="{py}" r="16" class="body"/>
  {_line(px,py,center_target[0],center_target[1],"중심방향", ORANGE, "arrowOrange", 3.0, "6 5", 10, -8)}
  {_line(px,py,gravity_end[0],gravity_end[1],"mg", BLUE, "arrowBlue")}
  {_line(px,py,tension_end[0],tension_end[1],"T 또는 N", GREEN, "arrowGreen", label_dx=12, label_dy=-14)}
  <line x1="280" y1="122" x2="348" y2="122" stroke="{GRAY}" stroke-width="2"/>
  {_text(318, 116, "R", MUTED, "math")}
  {_text(76, 218, "핵심: ΣF_radial = mv²/R", INK, "math")}
  {_text(76, 238, f"표시 위치: {pos_label}. 중심 방향을 +로 잡으세요.", MUTED, "note")}
  {_legend([("중력", BLUE), ("장력/수직항력", GREEN), ("중심방향", ORANGE)])}
"""
        return _svg_wrap(inner, 262, "vertical circle fbd")

    if st == "pure_rolling_energy":
        inner = f"""
  {_text(24, 35, "순수 구름 · 에너지와 구름 조건", INK, "title")}
  <polygon points="88,212 462,212 462,92" class="surface"/>
  <circle cx="270" cy="150" r="35" class="body"/>
  <circle cx="270" cy="150" r="5" fill="{BLUE}"/>
  <line x1="270" y1="150" x2="270" y2="185" stroke="{GRAY}" stroke-width="2"/>
  {_line(270,150,342,176,"v_G", ORANGE, "arrowOrange")}
  {_line(270,150,270,211,"mg", BLUE, "arrowBlue")}
  {_line(270,185,218,185,"f_s", RED, "arrowRed", 2.8, "5 5", -20, -8)}
  <path d="M252 127 A29 29 0 0 1 302 140" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(306, 137, "ω", PURPLE)}
  {_text(105, 240, "미끄럼 없음: v_G = ωR", INK, "math")}
  {_text(105, 258, "에너지: mgh = 1/2mv_G² + 1/2I_Gω²", INK, "math")}
  {_legend([("중력", BLUE), ("속도/운동", ORANGE), ("정지마찰", RED), ("회전", PURPLE)])}
"""
        return _svg_wrap(inner, 282, "pure rolling diagram")

    if st in {"spring_mass_vibration", "spring_energy"}:
        inner = f"""
  {_text(24, 35, "스프링-질량 · 복원력 방향", INK, "title")}
  <line x1="72" y1="63" x2="72" y2="188" stroke="{GRAY}" stroke-width="6" stroke-linecap="round"/>
  <polyline points="72,126 102,101 132,151 162,101 192,151 222,101 252,126" fill="none" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>
  <rect x="252" y="94" width="92" height="64" rx="13" class="body"/>
  <line x1="72" y1="194" x2="448" y2="194" stroke="{GRAY}" stroke-width="2"/>
  {_line(298,126,388,126,"+x", ORANGE, "arrowOrange", 2.7, "6 5")}
  {_line(298,126,212,126,"F_s=-kx", RED, "arrowRed")}
  {_line(298,126,298,178,"mg", BLUE, "arrowBlue")}
  {_line(298,126,298,75,"N", GREEN, "arrowGreen")}
  {_text(136, 178, "k", MUTED, "math")}
  {_text(286, 132, "m", MUTED, "math")}
  {_text(94, 224, "평형 위치 기준: m x¨ + kx = 0", INK, "math")}
  {_legend([("복원력", RED), ("좌표/변위", ORANGE), ("중력", BLUE), ("수직항력", GREEN)])}
"""
        return _svg_wrap(inner, 248, "spring mass fbd")

    if st == "flat_curve_friction":
        inner = f"""
  {_text(24, 35, "평평한 커브 · 마찰이 구심력", INK, "title")}
  <ellipse cx="275" cy="142" rx="128" ry="70" fill="none" stroke="{GRAY}" stroke-width="4" stroke-dasharray="10 7"/>
  <circle cx="275" cy="142" r="5" fill="{INK}"/>
  <rect x="374" y="125" width="50" height="32" rx="8" class="body"/>
  {_line(399,141,282,141,"f_s → 중심", RED, "arrowRed")}
  {_line(399,141,456,141,"v", ORANGE, "arrowOrange")}
  {_line(399,141,399,96,"N", GREEN, "arrowGreen")}
  {_line(399,141,399,191,"mg", BLUE, "arrowBlue")}
  {_text(94, 230, "한계 조건: f_s,max = μ_s N = mv²/R", INK, "math")}
  {_legend([("구심 마찰", RED), ("속도", ORANGE), ("수직항력", GREEN), ("중력", BLUE)])}
"""
        return _svg_wrap(inner, 252, "flat curve fbd")

    if st == "banked_curve_no_friction":
        theta = _q(c, "theta", 20.0) or 20.0
        theta_label = f"θ≈{theta:g}°" if "theta" in c.knowns else "θ"
        inner = f"""
  {_text(24, 35, "마찰 없는 뱅크 커브 · N 성분 분해", INK, "title")}
  <polygon points="92,202 466,202 466,112" class="surface"/>
  {_angle_arc(100, 202, 48, 0, 14, theta_label)}
  <g transform="translate(286 151) rotate(-15)"><rect x="-30" y="-19" width="60" height="38" rx="8" class="body"/></g>
  {_line(286,151,286,217,"mg", BLUE, "arrowBlue")}
  {_line(286,151,326,82,"N", GREEN, "arrowGreen")}
  {_line(286,151,345,151,"N sinθ → 중심", GREEN, "arrowGreen", 2.8, "6 5", 2, -12)}
  {_line(286,151,286,92,"N cosθ", GREEN, "arrowGreen", 2.8, "6 5", -82, -3)}
  {_line(286,151,354,121,"v", ORANGE, "arrowOrange")}
  {_text(90, 236, "수평: N sinθ = mv²/R, 수직: N cosθ = mg", INK, "math")}
  {_legend([("중력", BLUE), ("수직항력 성분", GREEN), ("속도", ORANGE)])}
"""
        return _svg_wrap(inner, 258, "banked curve fbd")

    if st == "polar_kinematics":
        inner = f"""
  {_text(24, 35, "극좌표 운동 · e_r / e_θ 성분", INK, "title")}
  <circle cx="150" cy="184" r="5" fill="{INK}"/>
  <circle cx="320" cy="105" r="17" class="body"/>
  <line x1="150" y1="184" x2="320" y2="105" stroke="{GRAY}" stroke-width="3"/>
  {_line(320,105,394,70,"e_r", GREEN, "arrowGreen")}
  {_line(320,105,353,180,"e_θ", ORANGE, "arrowOrange")}
  {_line(320,105,380,129,"r_dot", GREEN, "arrowGreen", 2.6, "6 5", 8, 16)}
  {_line(320,105,344,166,"rθ_dot", ORANGE, "arrowOrange", 2.6, "6 5", 4, 14)}
  <path d="M210 184 A80 80 0 0 1 250 128" fill="none" stroke="{PURPLE}" stroke-width="2.5" marker-end="url(#arrowPurple)"/>
  {_text(228, 157, "θ", PURPLE)}
  {_text(84, 228, "a_r = r¨ - rθ˙²", INK, "math")}
  {_text(84, 247, "a_θ = rθ¨ + 2r˙θ˙", INK, "math")}
  {_legend([("방사 방향", GREEN), ("횡방향", ORANGE), ("각도", PURPLE)])}
"""
        return _svg_wrap(inner, 268, "polar kinematics diagram")

    if st == "instant_center_velocity":
        inner = f"""
  {_text(24, 35, "순간중심 · 속도는 반지름에 수직", INK, "title")}
  <circle cx="148" cy="166" r="9" fill="{INK}"/>{_text(122, 194, "IC", MUTED, "label")}
  <circle cx="346" cy="96" r="17" class="body"/>{_text(370, 101, "P", MUTED, "label")}
  <line x1="148" y1="166" x2="346" y2="96" stroke="{GRAY}" stroke-width="3" stroke-dasharray="9 7"/>
  {_text(238, 119, "r", MUTED, "math")}
  {_line(346,96,382,199,"v_P = ωr", ORANGE, "arrowOrange")}
  <path d="M190 164 A78 78 0 0 1 224 120" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(208, 151, "ω", PURPLE)}
  {_text(82, 232, "속도 방향은 IC-P 선에 수직입니다.", INK, "math")}
  {_legend([("반지름", GRAY), ("속도", ORANGE), ("각속도", PURPLE)])}
"""
        return _svg_wrap(inner, 254, "instant center diagram")

    if st == "slot_pin_relative_motion":
        inner = f"""
  {_text(24, 35, "슬롯-핀 · 상대속도와 회전속도", INK, "title")}
  <g transform="rotate(-22 275 146)"><rect x="124" y="128" width="298" height="38" rx="19" fill="#eef4ff" stroke="{BLUE}" stroke-width="3"/><circle cx="308" cy="147" r="14" fill="#fff" stroke="{GREEN}" stroke-width="3"/></g>
  <circle cx="150" cy="196" r="5" fill="{INK}"/>
  <line x1="150" y1="196" x2="309" y2="148" stroke="{GRAY}" stroke-width="2.5" stroke-dasharray="8 7"/>
  {_line(309,148,386,117,"r_dot", GREEN, "arrowGreen")}
  {_line(309,148,350,224,"rω", ORANGE, "arrowOrange")}
  {_line(309,148,396,197,"v_abs", PURPLE, "arrowPurple", 2.8, "6 5", 6, 23)}
  <path d="M184 193 A83 83 0 0 1 210 136" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(203, 170, "ω", PURPLE)}
  {_text(78, 238, "|v|² = r˙² + (rω)²", INK, "math")}
  {_legend([("상대속도", GREEN), ("회전속도", ORANGE), ("절대속도", PURPLE)])}
"""
        return _svg_wrap(inner, 260, "slot pin diagram")

    if st == "plane_rigid_body_velocity":
        inner = f"""
  {_text(24, 35, "평면강체 · 두 점 속도 관계", INK, "title")}
  <rect x="154" y="92" width="230" height="92" rx="20" fill="#eef4ff" stroke="{BLUE}" stroke-width="3" filter="url(#softShadow)"/>
  <circle cx="202" cy="138" r="8" fill="{INK}"/>{_text(185, 165, "A", MUTED, "label")}
  <circle cx="336" cy="138" r="8" fill="{INK}"/>{_text(349, 165, "B", MUTED, "label")}
  <line x1="202" y1="138" x2="336" y2="138" stroke="{GRAY}" stroke-width="3" stroke-dasharray="8 6"/>
  {_text(256, 129, "r_B/A", MUTED, "math")}
  {_line(202,138,270,138,"v_A", GREEN, "arrowGreen")}
  {_line(336,138,336,60,"ω×r", ORANGE, "arrowOrange")}
  {_line(336,138,405,85,"v_B", PURPLE, "arrowPurple", 2.8, "6 5", 8, -4)}
  <path d="M245 190 A54 54 0 0 1 294 194" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(271, 216, "ω", PURPLE)}
  {_text(104, 235, "v_B = v_A + ω × r_B/A", INK, "math")}
  {_legend([("기준점 속도", GREEN), ("회전 기여", ORANGE), ("합성 속도", PURPLE)])}
"""
        return _svg_wrap(inner, 258, "plane rigid body velocity diagram")


    if st == "relative_acceleration_translation":
        inner = f"""
  {_text(24, 35, "상대가속도 · 병진 기준계", INK, "title")}
  <circle cx="170" cy="142" r="16" class="body"/>{_text(153, 176, "A", MUTED, "label")}
  <circle cx="350" cy="142" r="16" class="body"/>{_text(365, 176, "B", MUTED, "label")}
  <line x1="170" y1="142" x2="350" y2="142" stroke="{GRAY}" stroke-width="3" stroke-dasharray="8 6"/>
  {_line(170,142,245,96,"a_A", GREEN, "arrowGreen")}
  {_line(350,142,430,142,"a_B/A", ORANGE, "arrowOrange")}
  {_line(350,142,442,92,"a_B", PURPLE, "arrowPurple", 2.8, "6 5", 8, -4)}
  {_text(90, 222, "a_B = a_A + a_B/A", INK, "math")}
  {_legend([("기준점 가속도", GREEN), ("상대가속도", ORANGE), ("절대가속도", PURPLE)])}
"""
        return _svg_wrap(inner, 246, "relative acceleration diagram")

    if st == "coriolis_relative_motion":
        inner = f"""
  {_text(24, 35, "회전 기준계 · 코리올리 항", INK, "title")}
  <circle cx="154" cy="188" r="5" fill="{INK}"/>
  <line x1="154" y1="188" x2="334" y2="116" stroke="{GRAY}" stroke-width="3" stroke-dasharray="8 7"/>
  <circle cx="334" cy="116" r="16" class="body"/>
  {_line(334,116,420,82,"v_rel", GREEN, "arrowGreen")}
  {_line(334,116,374,206,"2ωv_rel", RED, "arrowRed")}
  {_line(334,116,258,148,"rω²", ORANGE, "arrowOrange")}
  <path d="M196 184 A90 90 0 0 1 236 126" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(220, 160, "ω", PURPLE)}
  {_text(82, 236, "a = α×r + ω×(ω×r) + 2ω×v_rel + a_rel", INK, "math")}
  {_legend([("상대속도", GREEN), ("코리올리", RED), ("법선항", ORANGE), ("회전", PURPLE)])}
"""
        return _svg_wrap(inner, 260, "coriolis acceleration diagram")

    if st == "plane_rigid_body_acceleration":
        inner = f"""
  {_text(24, 35, "평면강체 · 두 점 가속도 관계", INK, "title")}
  <rect x="150" y="92" width="240" height="92" rx="20" fill="#eef4ff" stroke="{BLUE}" stroke-width="3" filter="url(#softShadow)"/>
  <circle cx="202" cy="138" r="8" fill="{INK}"/>{_text(185, 165, "A", MUTED, "label")}
  <circle cx="342" cy="138" r="8" fill="{INK}"/>{_text(355, 165, "B", MUTED, "label")}
  <line x1="202" y1="138" x2="342" y2="138" stroke="{GRAY}" stroke-width="3" stroke-dasharray="8 6"/>
  {_line(342,138,342,64,"αr", GREEN, "arrowGreen")}
  {_line(342,138,238,138,"ω²r", ORANGE, "arrowOrange")}
  {_line(202,138,250,88,"a_A", PURPLE, "arrowPurple", 2.8, "6 5")}
  {_text(92, 232, "a_B = a_A + α×r_B/A + ω×(ω×r_B/A)", INK, "math")}
  {_legend([("접선 αr", GREEN), ("법선 ω²r", ORANGE), ("기준점", PURPLE)])}
"""
        return _svg_wrap(inner, 256, "plane rigid body acceleration diagram")

    if st == "massive_pulley_atwood":
        inner = f"""
  {_text(24, 35, "질량 있는 도르래 · T1과 T2 분리", INK, "title")}
  <circle cx="280" cy="92" r="42" fill="#fff" stroke="{BLUE}" stroke-width="4" filter="url(#softShadow)"/>
  <circle cx="280" cy="92" r="6" fill="{BLUE}"/>
  <path d="M238 92 L238 184 M322 92 L322 184" stroke="{INK}" stroke-width="3"/>
  <rect x="202" y="184" width="72" height="48" rx="10" class="body"/>
  <rect x="286" y="184" width="72" height="48" rx="10" class="body"/>
  {_line(238,208,238,150,"T1", GREEN, "arrowGreen")}
  {_line(322,208,322,150,"T2", GREEN, "arrowGreen")}
  {_line(238,208,238,252,"m1g", BLUE, "arrowBlue")}
  {_line(322,208,322,252,"m2g", BLUE, "arrowBlue")}
  <path d="M296 53 A42 42 0 0 1 322 92" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(316, 58, "α", PURPLE)}
  {_text(82, 276, "(T2-T1)R=Iα,  a=αR", INK, "math")}
  {_legend([("장력", GREEN), ("중력", BLUE), ("회전", PURPLE)])}
"""
        return _svg_wrap(inner, 300, "massive pulley diagram")

    if st == "rolling_energy_general":
        inner = f"""
  {_text(24, 35, "일반 순수 구름 · 주어진 I 사용", INK, "title")}
  <polygon points="92,212 462,212 462,92" class="surface"/>
  <circle cx="270" cy="150" r="35" class="body"/>
  <circle cx="270" cy="150" r="5" fill="{BLUE}"/>
  {_line(270,150,342,176,"v_G", ORANGE, "arrowOrange")}
  <path d="M252 127 A29 29 0 0 1 302 140" fill="none" stroke="{PURPLE}" stroke-width="3" marker-end="url(#arrowPurple)"/>
  {_text(306, 137, "ω", PURPLE)}
  {_line(270,150,270,211,"mg", BLUE, "arrowBlue")}
  {_text(102, 240, "mgh = 1/2mv² + 1/2Iω²,  v=ωR", INK, "math")}
  {_legend([("중력", BLUE), ("병진속도", ORANGE), ("회전", PURPLE)])}
"""
        return _svg_wrap(inner, 264, "general rolling energy diagram")

    return None
