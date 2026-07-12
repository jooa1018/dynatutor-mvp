"""역대입(back-substitution) 잔차 검증.

solver가 낸 답을 지배 방정식에 다시 넣어 잔차 |r| ≈ 0 인지 확인한다.
solver의 대수 실수, 단위 슬립, 잘못된 근 선택, (온도 버그처럼) 오염된
knowns로 계산된 답을 — 답이 사용자에게 나가기 전에 — 잡는 층이다.

각 검사는 '풀이 공식의 재실행'이 아니라 '지배 방정식에의 대입'이다.
예: Atwood는 a=(m2-m1)g/(m1+m2)를 다시 계산하지 않고,
    두 물체 각각의 뉴턴 방정식 잔차 (m_heavy·g - T - m_heavy·a)와
    (T - m_light·g - m_light·a)를 검사한다. 답 a와 T가 함께 맞아야 통과.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable

from engine.models import CanonicalProblem
from engine.physics_core.units import magnitude_si
from engine.physics_core.direction_parser import infer_angle_between_force_and_displacement
from engine.physics_core.initial_conditions import explicitly_starts_from_angular_rest, explicitly_starts_from_rest

REL_TOL = 1e-4  # solver numeric은 ~6유효숫자 반올림 → 1e-6은 무고 오탐. 1e-4는 반올림은 통과, 실수(≥0.1%)는 검출.
ABS_TOL = 1e-8


@dataclass
class ResidualCheck:
    name: str
    residual: float
    scale: float

    @property
    def passed(self) -> bool:
        return abs(self.residual) <= ABS_TOL + REL_TOL * max(self.scale, 1.0)

    def describe(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"역대입: {self.name} |r|={abs(self.residual):.3g} (scale {self.scale:.3g}) {status}"


def _k(cp: CanonicalProblem, key: str, unit: str) -> float | None:
    q = cp.knowns.get(key)
    if q is None or q.value is None:
        return None
    try:
        return magnitude_si(q, unit)
    except Exception:
        return None


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _explicitly_starts_from_rest(cp: CanonicalProblem) -> bool:
    raw = (cp.raw_text or "").lower()
    return any(
        phrase in raw
        for phrase in (
            "정지 상태에서",
            "정지 상태의",
            "정지 상태인",
            "처음에 정지한",
            "정지한 물체",
            "정지 상태로부터",
            "정지에서",
            "처음에는 정지",
            "초기에는 정지",
            "가만히 있다가",
            "starts from rest",
            "initially at rest",
        )
    )


def _theta_rad(cp: CanonicalProblem) -> float | None:
    if cp.launch_angle_deg is not None:
        return math.radians(float(cp.launch_angle_deg))
    th = _k(cp, "theta", "deg")
    return math.radians(th) if th is not None else None


def _mu(cp: CanonicalProblem) -> float:
    for key in ("mu_k", "mu"):
        v = _k(cp, key, "")
        if v is not None:
            return v
    return 0.0


# --------------------------------------------------------------- checkers
def _incline(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    a, g, th = pool.get("a"), _k(cp, "g", "m/s^2"), _theta_rad(cp)
    if a is None or g is None or th is None:
        return []
    mu = 0.0 if cp.subtype == "no_friction" else _mu(cp)
    # 정지마찰이 버티는 경우 a=0: 미끄러짐 방정식 a=g(sinθ-μcosθ)는 적용되지 않는다
    # (정지마찰은 필요한 만큼 조정됨). 이때는 정지 조건 μ_s ≥ tanθ 를 검사한다.
    if abs(a) < 1e-9:
        mu_s = _first_not_none(_k(cp, "mu_s", ""), _k(cp, "mu", ""), mu)
        # tanθ ≤ μ_s 이면 정지가 물리적으로 타당 → 통과. 잔차는 위반량(초과분).
        violation = max(0.0, math.tan(th) - mu_s)
        return [ResidualCheck("정지 조건 tanθ ≤ μ_s (a=0)", violation, 1.0)]
    expected_term = g * (math.sin(th) - mu * math.cos(th))
    return [ResidualCheck("경사면 뉴턴식 a - g(sinθ - μcosθ)", a - expected_term, max(abs(a), abs(expected_term)))]


def _atwood(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    a, T = pool.get("a"), pool.get("T")
    m1, m2, g = _k(cp, "m1", "kg"), _k(cp, "m2", "kg"), _k(cp, "g", "m/s^2")
    if None in (a, T, m1, m2, g):
        return []
    # 좌표 계약: m2 아래/m1 위가 +a. 음수 a는 실제 방향이 반대임을 뜻한다.
    return [
        ResidualCheck("m1: T - m1g - m1a", T - m1 * g - m1 * a, max(abs(T), m1 * g, 1.0)),
        ResidualCheck("m2: m2g - T - m2a", m2 * g - T - m2 * a, max(abs(T), m2 * g, 1.0)),
    ]


def _table_hanging(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    a, T = pool.get("a"), pool.get("T")
    m1, m2, g = _k(cp, "m1", "kg"), _k(cp, "m2", "kg"), _k(cp, "g", "m/s^2")
    if None in (a, T, m1, m2, g):
        return []
    if abs(a) < 1e-9:
        checks = [
            ResidualCheck(
                "정지 매달린 물체: T = m2g",
                T - m2 * g,
                max(abs(T), m2 * g, 1.0),
            )
        ]
        f_s = pool.get("f_s")
        if f_s is not None:
            checks.append(
                ResidualCheck(
                    "정지 테이블 물체: |f_s| = |T|",
                    abs(f_s) - abs(T),
                    max(abs(T), 1.0),
                )
            )
        mu_s = _first_not_none(_k(cp, "mu_s", ""), _k(cp, "mu", ""))
        if mu_s is not None:
            max_static = mu_s * m1 * g
            checks.append(
                ResidualCheck(
                    "정지마찰 한계: |T| ≤ μ_s m1g",
                    max(0.0, abs(T) - max_static),
                    max(max_static, 1.0),
                )
            )
        return checks
    mu = _mu(cp)
    checks = [
        ResidualCheck("매달린 물체: m2·g - T - m2·a", m2 * g - T - m2 * a, m2 * g),
        ResidualCheck("테이블 물체: T - μm1g - m1·a", T - mu * m1 * g - m1 * a, abs(T) + m1 * g),
    ]
    f_k = pool.get("f_k")
    if f_k is not None:
        expected_friction = mu * m1 * g
        checks.append(
            ResidualCheck(
                "운동마찰력: f_k = μ_k m1g",
                f_k - expected_friction,
                max(abs(expected_friction), 1.0),
            )
        )
    return checks


def _incline_hanging(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    a, T = pool.get("a"), pool.get("T")
    m1, m2, g, th = _k(cp, "m1", "kg"), _k(cp, "m2", "kg"), _k(cp, "g", "m/s^2"), _theta_rad(cp)
    if None in (a, T, m1, m2, g) or th is None:
        return []
    mu = _mu(cp)
    # 정지마찰이 버텨 a=0인 경우: 미끄러짐 방정식이 적용되지 않는다.
    # 매달린 물체 정지조건 T=m2·g, 경사면 물체는 정지마찰이 |m2g - m1g·sinθ| ≤ μs·m1g·cosθ
    # 를 만족하면 타당. 잔차는 위반량.
    if abs(a) < 1e-9:
        mu_s = _first_not_none(_k(cp, "mu_s", ""), _k(cp, "mu", ""), mu)
        required_static = abs(m2 * g - m1 * g * math.sin(th))
        max_static = mu_s * m1 * g * math.cos(th)
        checks = [
            ResidualCheck(
                "정지 매달린 물체: T = m2g",
                T - m2 * g,
                max(abs(T), m2 * g, 1.0),
            ),
            ResidualCheck(
                "정지 조건 |m2g - m1g·sinθ| ≤ μs·m1g·cosθ (a=0)",
                max(0.0, required_static - max_static),
                max_static + 1.0,
            ),
        ]
        f_s = pool.get("f_s")
        if f_s is not None:
            checks.append(
                ResidualCheck(
                    "정지 경사면 물체: |f_s| = |m2g-m1g sinθ|",
                    abs(f_s) - required_static,
                    max(required_static, 1.0),
                )
            )
        return checks
    # 방향 관례가 solver와 다를 수 있으므로 두 부호 중 잔차가 작은 쪽을 채택하되,
    # 채택 후에도 두 방정식이 '동시에' 맞아야 통과한다.
    # 방향 관례가 solver와 다를 수 있다: 가속도 부호와 마찰 부호(운동 방향에 반대)를
    # 모두 시도하고, 두 물체 방정식이 동시에 성립하는 조합이 있으면 통과.
    # (마찰은 항상 상대운동 반대 → m1이 내려가면 위로, 올라가면 아래로.)
    best = None
    for a_sign in (+1.0, -1.0):
        for f_sign in (+1.0, -1.0):
            aa = a_sign * a
            hang = ResidualCheck("매달린 물체: m2·g - T - m2·a", m2 * g - T - m2 * aa, m2 * g)
            incl = ResidualCheck(
                "경사면 물체: T - m1·g·sinθ + f_sign·μm1g·cosθ - m1·a",
                T - m1 * g * math.sin(th) + f_sign * mu * m1 * g * math.cos(th) - m1 * aa,
                abs(T) + m1 * g,
            )
            total = abs(hang.residual) + abs(incl.residual)
            if best is None or total < best[0]:
                best = (total, [hang, incl])
    checks = best[1]
    f_k = pool.get("f_k")
    if f_k is not None:
        expected_friction = mu * m1 * g * math.cos(th)
        checks.append(
            ResidualCheck(
                "경사면 운동마찰력: f_k = μ_k m1g cosθ",
                f_k - expected_friction,
                max(abs(expected_friction), 1.0),
            )
        )
    return checks


def _projectile(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    g = _k(cp, "g", "m/s^2")
    v0 = _first_not_none(_k(cp, "v0", "m/s"), _k(cp, "v", "m/s"))
    th = _theta_rad(cp)
    if g is None or v0 is None or th is None:
        return []
    y0 = cp.launch_height if cp.launch_height is not None else _first_not_none(_k(cp, "h", "m"), 0.0)
    y_final = cp.landing_height
    if y_final is None:
        raw = (cp.raw_text or "").lower()
        y_final = y0 if "같은 높이" in raw else 0.0
    vx, vy = v0 * math.cos(th), v0 * math.sin(th)
    t, R = pool.get("t"), pool.get("R")
    if t is None and R is not None and abs(vx) > 1e-12:
        t = R / vx  # x-식으로 유도한 t를 y-식에 대입 — 결합 항등식 검사
    checks: list[ResidualCheck] = []
    if t is not None:
        checks.append(ResidualCheck(
            "포물선 y(t) = y_final",
            (y0 + vy * t - 0.5 * g * t * t) - y_final,
            max(abs(y0), abs(y_final), 0.5 * g * t * t, 1.0),
        ))
    if t is not None and R is not None:
        checks.append(ResidualCheck("포물선 R - vₓ·t", R - vx * t, max(abs(R), 1.0)))
    hmax = _first_not_none(pool.get("H"), pool.get("h_max"))
    if hmax is not None:
        checks.append(ResidualCheck("최대높이 H - vy²/2g - y0", hmax - (y0 + vy * vy / (2 * g)), max(abs(hmax), 1.0)))
    return checks


def _collision(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    m1, m2 = _k(cp, "m1", "kg"), _k(cp, "m2", "kg")
    v1, v2 = _k(cp, "v1", "m/s"), _k(cp, "v2", "m/s")
    if None in (m1, m2, v1):
        return []
    v2 = _first_not_none(v2, 0.0)
    p_before = m1 * v1 + m2 * v2
    vf = _first_not_none(pool.get("v_f"), pool.get("vf"))
    v1p = _first_not_none(pool.get("v1'"), pool.get("v1p"))
    v2p = _first_not_none(pool.get("v2'"), pool.get("v2p"))
    checks: list[ResidualCheck] = []
    if vf is not None:  # 완전비탄성
        checks.append(ResidualCheck("운동량 보존(완전비탄성)", p_before - (m1 + m2) * vf, abs(p_before) + 1.0))
    elif v1p is not None and v2p is not None:
        checks.append(ResidualCheck("운동량 보존", p_before - (m1 * v1p + m2 * v2p), abs(p_before) + 1.0))
        restitution = _k(cp, "e", "")
        elastic_mode = bool((cp.flags or {}).get("elastic")) and (
            restitution is None or math.isclose(restitution, 1.0, abs_tol=1e-12)
        )
        if elastic_mode:
            ke_b = 0.5 * m1 * v1 * v1 + 0.5 * m2 * v2 * v2
            ke_a = 0.5 * m1 * v1p * v1p + 0.5 * m2 * v2p * v2p
            checks.append(ResidualCheck("운동에너지 보존(탄성)", ke_b - ke_a, ke_b + 1.0))
    return checks


def _const_acc(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    v0 = _first_not_none(_k(cp, "v0", "m/s"), pool.get("v0"))
    vf = _first_not_none(pool.get("vf"), pool.get("v_f"), _k(cp, "vf", "m/s"))
    a = _first_not_none(pool.get("a"), _k(cp, "a", "m/s^2"))
    t = _first_not_none(pool.get("t"), _k(cp, "t", "s"))
    s = _first_not_none(pool.get("s"), _k(cp, "s", "m"))
    checks: list[ResidualCheck] = []

    if None not in (vf, v0, a, t):
        expected = v0 + a * t
        checks.append(
            ResidualCheck(
                "v_f = v0 + a·t",
                vf - expected,
                max(abs(vf), abs(expected), 1.0),
            )
        )
    if None not in (s, v0, a, t):
        expected = v0 * t + 0.5 * a * t * t
        checks.append(
            ResidualCheck(
                "s = v0t + ½at²",
                s - expected,
                max(abs(s), abs(expected), 1.0),
            )
        )
    if None not in (vf, v0, a, s):
        left = vf * vf
        right = v0 * v0 + 2 * a * s
        checks.append(
            ResidualCheck(
                "v_f² = v0² + 2as",
                left - right,
                max(abs(left), abs(right), 1.0),
            )
        )
    if None not in (s, v0, vf, t):
        expected = 0.5 * (v0 + vf) * t
        checks.append(
            ResidualCheck(
                "s = ½(v0+vf)t",
                s - expected,
                max(abs(s), abs(expected), 1.0),
            )
        )
    return checks


def _work_energy(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    m, W = _k(cp, "m", "kg"), _k(cp, "W", "J")
    if W is None:
        F, s = _k(cp, "F", "N"), _k(cp, "s", "m")
        angle = infer_angle_between_force_and_displacement(cp.raw_text)
        if angle is None:
            angle = _k(cp, "theta", "deg")
        W = (
            F * s * math.cos(math.radians(angle))
            if None not in (F, s, angle)
            else None
        )
    v = _first_not_none(pool.get("v_f"), pool.get("vf"), pool.get("v"))
    if None in (m, W) or v is None:
        return []
    v0 = _first_not_none(_k(cp, "v0", "m/s"), _k(cp, "v", "m/s"))
    if v0 is None and _explicitly_starts_from_rest(cp):
        v0 = 0.0
    if v0 is None:
        return []
    return [ResidualCheck("일-에너지: W - ½m(v² - v0²)", W - 0.5 * m * (v * v - v0 * v0), abs(W) + 1.0)]


def _spring_energy(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    E = pool.get("E")
    k_e, x_e = _k(cp, "k", "N/m"), _first_not_none(_k(cp, "x", "m"), _k(cp, "A", "m"))
    if E is not None and None not in (k_e, x_e):
        expected = 0.5 * k_e * x_e * x_e
        return [ResidualCheck("탄성 에너지: E - ½kx²", E - expected, max(expected, 1.0))]
    k, m, x = _k(cp, "k", "N/m"), _k(cp, "m", "kg"), _first_not_none(_k(cp, "x", "m"), _k(cp, "A", "m"))
    v = _first_not_none(pool.get("v"), pool.get("v_f"), pool.get("vf"))
    if None in (k, m, x) or v is None:
        return []
    return [ResidualCheck("에너지: ½kx² - ½mv²", 0.5 * k * x * x - 0.5 * m * v * v, 0.5 * k * x * x + 1.0)]


def _spring_vibration(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    k, m = _k(cp, "k", "N/m"), _k(cp, "m", "kg")
    if None in (k, m):
        return []
    checks: list[ResidualCheck] = []
    omega = _first_not_none(pool.get("omega"), pool.get("omega_n"))
    if omega is not None:
        checks.append(ResidualCheck("고유진동수: ω²m - k", omega * omega * m - k, k + 1.0))
    T = pool.get("T")  # 주기 (진동 문맥에서 T는 장력이 아니라 주기)
    if T is not None and T > 0:
        checks.append(ResidualCheck("주기: T·√(k/m) - 2π", T * math.sqrt(k / m) - 2 * math.pi, 2 * math.pi))
    frequency = pool.get("f")
    if frequency is not None:
        expected = math.sqrt(k / m) / (2 * math.pi)
        checks.append(ResidualCheck("진동수: f - √(k/m)/(2π)", frequency - expected, max(abs(expected), 1.0)))
    return checks


def _const_force_work(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    F, s = _k(cp, "F", "N"), _k(cp, "s", "m")
    W = pool.get("W")
    if None in (F, s) or W is None:
        return []
    th = _theta_rad(cp)
    if th is None:
        angle = infer_angle_between_force_and_displacement(cp.raw_text)
        th = math.radians(angle) if angle is not None else None
    if th is None:
        return []
    magnitude = abs(F * s * math.cos(th))
    # 부호 관례가 solver마다 다르다(마찰/저항일은 음수로 인코딩, θ로 인코딩, 또는 둘 다).
    # 따라서 크기만 항등식으로 검사하고, 부호 타당성은 별도로 본다.
    checks = [ResidualCheck("|W| - |F·s·cosθ|", abs(W) - magnitude, magnitude + 1.0)]
    raw = cp.raw_text or ""
    opposing = any(w in raw for w in ["반대로", "반대 방향", "저항", "마찰력이 한 일", "opposing", "against"])
    if opposing and W > 0 and magnitude > 1e-9:
        checks.append(ResidualCheck("저항일 부호(음수 기대)", W, magnitude))
    return checks


def _impulse(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    F, t = _k(cp, "F", "N"), _k(cp, "t", "s")
    J = pool.get("J")
    checks: list[ResidualCheck] = []
    if J is not None and None not in (F, t):
        checks.append(ResidualCheck("J - F·Δt", J - F * t, abs(F * t) + 1.0))
    vf = _first_not_none(pool.get("v_f"), pool.get("vf"))
    m = _k(cp, "m", "kg")
    v0 = _first_not_none(_k(cp, "v0", "m/s"), _k(cp, "v", "m/s"))
    if v0 is None and explicitly_starts_from_rest(cp):
        v0 = 0.0
    if vf is not None and None not in (F, t, m, v0):
        checks.append(ResidualCheck("충격량-운동량: F·Δt - m(v - v0)", F * t - m * (vf - v0), abs(F * t) + 1.0))
    return checks


def _fixed_axis(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    checks: list[ResidualCheck] = []
    tau, I = _k(cp, "tau", "N*m"), _k(cp, "I", "kg*m^2")
    alpha = pool.get("alpha")
    if alpha is not None and None not in (tau, I):
        checks.append(ResidualCheck("고정축 회전: I·α - τ", I * alpha - tau, abs(tau) + 1.0))
    # Phase 39: 회전 kinematics 답 (ω = ω₀ + αt, v = ωr)
    omega_f = pool.get("omega_f")
    a_k, t_k = _k(cp, "alpha", "rad/s^2"), _k(cp, "t", "s")
    if omega_f is not None and None not in (a_k, t_k):
        omega0 = _first_not_none(
            _k(cp, "omega0", "rad/s"),
            _k(cp, "omega", "rad/s"),
        )
        if omega0 is None and explicitly_starts_from_angular_rest(cp):
            omega0 = 0.0
        if omega0 is not None:
            expected = omega0 + a_k * t_k
            checks.append(
                ResidualCheck(
                    "회전 kinematics: ω - (ω₀+αt)",
                    omega_f - expected,
                    max(abs(expected), 1.0),
                )
            )
    v = pool.get("v")
    om, r = _k(cp, "omega", "rad/s"), _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"))
    if v is not None and None not in (om, r) and a_k is None:
        expected = om * r
        checks.append(ResidualCheck("회전점 속력: v - ωr", v - expected, max(abs(expected), 1.0)))
    return checks


def _horizontal_friction(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    mu = _first_not_none(_k(cp, "mu_k", ""), _k(cp, "mu", ""))
    m = _k(cp, "m", "kg")
    if m is None and "m2" not in (cp.knowns or {}):
        m = _k(cp, "m1", "kg")
    g = _k(cp, "g", "m/s^2")
    f = pool.get("f")
    if f is None or None in (m, g, mu):
        return []
    checks = [ResidualCheck("수평 마찰력: f - μmg", f - mu * m * g, max(mu * m * g, 1.0))]
    N = pool.get("N")
    if N is not None:
        checks.append(ResidualCheck("수직항력: N - mg", N - m * g, max(m * g, 1.0)))
    return checks


def _rolling(cp: CanonicalProblem, pool: dict, beta: float | None) -> list[ResidualCheck]:
    g, h = _k(cp, "g", "m/s^2"), _first_not_none(_k(cp, "h", "m"), cp.launch_height)
    v = _first_not_none(pool.get("v"), pool.get("v_f"), pool.get("vf"))
    if None in (g, h) or v is None or beta is None:
        return []
    v0 = _first_not_none(_k(cp, "v0", "m/s"), _k(cp, "v", "m/s"))
    if v0 is None and explicitly_starts_from_rest(cp):
        v0 = 0.0
    if v0 is None:
        return []
    residual = 0.5 * (v * v - v0 * v0) * (1 + beta) - g * h
    return [ResidualCheck("구름 에너지: ½(v²-v0²)(1+β) - gh", residual, g * h + 0.5 * v0 * v0 * (1 + beta) + 1.0)]


def _curve_flat(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    g, r = _k(cp, "g", "m/s^2"), _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"))
    mu = _first_not_none(_k(cp, "mu_k", ""), _k(cp, "mu", ""))
    v = _first_not_none(pool.get("v_max"), pool.get("v"))
    if None in (g, r, mu) or v is None:
        return []
    return [ResidualCheck("평면 커브: v² - μgr", v * v - mu * g * r, mu * g * r + 1.0)]


def _curve_banked(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    g, r, th = _k(cp, "g", "m/s^2"), _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m")), _theta_rad(cp)
    v = _first_not_none(pool.get("v"), pool.get("v_max"))
    if None in (g, r) or th is None or v is None:
        return []
    return [ResidualCheck("뱅크 커브: v² - gr·tanθ", v * v - g * r * math.tan(th), g * r * math.tan(th) + 1.0)]


def _polar(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    r = _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"))
    thetadot = _first_not_none(_k(cp, "thetadot", "rad/s"), _k(cp, "omega", "rad/s"))
    if r is None or thetadot is None:
        return []
    rdot = _first_not_none(_k(cp, "rdot", "m/s"), 0.0)
    checks: list[ResidualCheck] = []
    v_r, v_t, v = pool.get("v_r"), pool.get("v_theta"), pool.get("v")
    if v_r is not None:
        checks.append(ResidualCheck("극좌표 v_r - ṙ", v_r - rdot, max(abs(rdot), 1.0)))
    if v_t is not None:
        checks.append(ResidualCheck("극좌표 v_θ - r·θ̇", v_t - r * thetadot, max(abs(r * thetadot), 1.0)))
    if v is not None and v_r is not None and v_t is not None:
        checks.append(ResidualCheck("극좌표 |v|² - (v_r²+v_θ²)", v * v - (v_r * v_r + v_t * v_t), v * v + 1.0))
    a_r, a_t, a = pool.get("a_r"), pool.get("a_theta"), pool.get("a")
    if a_r is not None or a_t is not None:
        rddot = _first_not_none(_k(cp, "rddot", "m/s^2"), 0.0)
        thetaddot = _first_not_none(_k(cp, "thetaddot", "rad/s^2"), _k(cp, "alpha", "rad/s^2"), 0.0)
        if a_r is not None:
            expected = rddot - r * thetadot * thetadot
            checks.append(ResidualCheck("극좌표 a_r - (r̈ - rθ̇²)", a_r - expected, max(abs(expected), 1.0)))
        if a_t is not None:
            expected = r * thetaddot + 2 * rdot * thetadot
            checks.append(ResidualCheck("극좌표 a_θ - (rθ̈ + 2ṙθ̇)", a_t - expected, max(abs(expected), 1.0)))
        if a is not None and a_r is not None and a_t is not None:
            checks.append(ResidualCheck("극좌표 |a|² - (a_r²+a_θ²)", a * a - (a_r * a_r + a_t * a_t), a * a + 1.0))
    return checks


def _coriolis(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    omega = _first_not_none(_k(cp, "omega", "rad/s"), _k(cp, "thetadot", "rad/s"))
    vrel = _first_not_none(_k(cp, "vrel", "m/s"), _k(cp, "rdot", "m/s"))
    if omega is None or vrel is None:
        return []
    checks: list[ResidualCheck] = []
    a_c = pool.get("a_C")
    if a_c is not None:
        expected = 2 * omega * vrel
        checks.append(ResidualCheck("코리올리 a_C - 2ωv_rel", a_c - expected, max(abs(expected), 1.0)))
    r = _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"), 0.0)
    a_r, a_t, a = pool.get("a_r"), pool.get("a_theta"), pool.get("a")
    if r is not None and a_r is not None:
        a_rel = _first_not_none(_k(cp, "arel", "m/s^2"), _k(cp, "rddot", "m/s^2"), 0.0)
        expected = a_rel - r * omega * omega
        checks.append(ResidualCheck("회전계 a_r - (a_rel - rω²)", a_r - expected, max(abs(expected), 1.0)))
    if r is not None and a_t is not None and a_c is not None:
        alpha = _first_not_none(_k(cp, "alpha", "rad/s^2"), _k(cp, "thetaddot", "rad/s^2"), 0.0)
        expected = r * alpha + a_c
        checks.append(ResidualCheck("회전계 a_θ - (rα + a_C)", a_t - expected, max(abs(expected), 1.0)))
    if a is not None and a_r is not None and a_t is not None:
        checks.append(ResidualCheck("회전계 |a|² - (a_r²+a_θ²)", a * a - (a_r * a_r + a_t * a_t), a * a + 1.0))
    return checks


def _rigid_rBA(cp: CanonicalProblem):
    cd = getattr(cp, "coordinate_data", {}) or {}
    if "rBAx" in cd and "rBAy" in cd:
        return float(cd["rBAx"]), float(cd["rBAy"])
    rx, ry = _k(cp, "rBAx", "m"), _k(cp, "rBAy", "m")
    if rx is not None and ry is not None:
        return rx, ry
    return None


def _rigid_radius(cp: CanonicalProblem) -> float | None:
    rba = _rigid_rBA(cp)
    if rba is not None:
        return math.hypot(*rba)
    return _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"))


def _rigid_reference_vector(cp: CanonicalProblem, prefix: str, unit: str):
    cd = getattr(cp, "coordinate_data", {}) or {}
    x_key, y_key = f"{prefix}Ax", f"{prefix}Ay"
    if x_key in cd and y_key in cd:
        return float(cd[x_key]), float(cd[y_key])
    x_value, y_value = _k(cp, x_key, unit), _k(cp, y_key, unit)
    if x_value is not None and y_value is not None:
        return x_value, y_value
    scalar = _k(cp, f"{prefix}A", unit)
    raw = cp.raw_text or ""
    fixed = any(
        phrase in raw
        for phrase in ("고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed")
    )
    if fixed or (scalar is not None and abs(scalar) <= 1e-12):
        return 0.0, 0.0
    return None


def _rigid_velocity(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    omega = _k(cp, "omega", "rad/s")
    radius = _rigid_radius(cp)
    if omega is None or radius is None:
        return []
    cd = getattr(cp, "coordinate_data", {}) or {}
    omega_sign = _first_not_none(cd.get("omega_sign"), cd.get("angular_sign"))
    w = float(omega_sign) * omega if omega_sign is not None else None
    rba = _rigid_rBA(cp)
    reference = _rigid_reference_vector(cp, "v", "m/s")
    vBx, vBy, vB = pool.get("v_Bx"), pool.get("v_By"), pool.get("v_B")
    checks: list[ResidualCheck] = []

    if rba is not None and reference is not None and w is not None:
        vAx, vAy = reference
        rx, ry = rba
        if vBx is not None:
            expected = vAx - w * ry
            checks.append(ResidualCheck("강체 v_Bx - (v_Ax - ω·r_y)", vBx - expected, max(abs(vAx), abs(w * ry), abs(expected), 1.0)))
        if vBy is not None:
            expected = vAy + w * rx
            checks.append(ResidualCheck("강체 v_By - (v_Ay + ω·r_x)", vBy - expected, max(abs(vAy), abs(w * rx), abs(expected), 1.0)))
    if vB is not None and vBx is not None and vBy is not None:
        checks.append(ResidualCheck("강체 |v_B|² - (v_Bx²+v_By²)", vB * vB - (vBx * vBx + vBy * vBy), vB * vB + 1.0))
    elif vB is not None and reference == (0.0, 0.0):
        expected = abs(omega) * radius
        checks.append(ResidualCheck("고정 A 강체 속력: |v_B| - |ω|r", vB - expected, max(abs(expected), 1.0)))
    return checks


def _rigid_acceleration(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    omega = _k(cp, "omega", "rad/s")
    alpha = _k(cp, "alpha", "rad/s^2")
    radius = _rigid_radius(cp)
    if omega is None or alpha is None or radius is None:
        return []
    cd = getattr(cp, "coordinate_data", {}) or {}
    omega_sign = _first_not_none(cd.get("omega_sign"), cd.get("angular_sign"))
    alpha_sign = _first_not_none(cd.get("alpha_sign"), cd.get("angular_sign"))
    w = float(omega_sign) * omega if omega_sign is not None else None
    al = float(alpha_sign) * alpha if alpha_sign is not None else None
    checks: list[ResidualCheck] = []
    a_t, a_n = pool.get("a_t"), pool.get("a_n")
    if a_t is not None:
        expected = abs(alpha) * radius
        checks.append(ResidualCheck("강체 a_t - |α|·r", a_t - expected, max(abs(expected), 1.0)))
    if a_n is not None:
        expected = omega * omega * radius
        checks.append(ResidualCheck("강체 a_n - ω²·r", a_n - expected, max(abs(expected), 1.0)))

    rba = _rigid_rBA(cp)
    reference = _rigid_reference_vector(cp, "a", "m/s^2")
    aBx, aBy, aB = pool.get("a_Bx"), pool.get("a_By"), pool.get("a_B")
    if rba is not None and reference is not None and w is not None and al is not None:
        aAx, aAy = reference
        rx, ry = rba
        if aBx is not None:
            expected = aAx - al * ry - w * w * rx
            checks.append(ResidualCheck("강체 a_Bx - (a_Ax - α·r_y - ω²r_x)", aBx - expected, max(abs(aAx), abs(al * ry), abs(w * w * rx), abs(expected), 1.0)))
        if aBy is not None:
            expected = aAy + al * rx - w * w * ry
            checks.append(ResidualCheck("강체 a_By - (a_Ay + α·r_x - ω²r_y)", aBy - expected, max(abs(aAy), abs(al * rx), abs(w * w * ry), abs(expected), 1.0)))
    if aB is not None and aBx is not None and aBy is not None:
        checks.append(ResidualCheck("강체 |a_B|² - (a_Bx²+a_By²)", aB * aB - (aBx * aBx + aBy * aBy), aB * aB + 1.0))
    elif aB is not None and reference == (0.0, 0.0):
        expected_squared = (alpha * radius) ** 2 + (omega * omega * radius) ** 2
        checks.append(ResidualCheck("고정 A 강체 가속도 크기", aB * aB - expected_squared, max(expected_squared, 1.0)))
    return checks


def _single_particle(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    m = _first_not_none(_k(cp, "m", "kg"), pool.get("m"))
    force = _first_not_none(_k(cp, "F", "N"), pool.get("F"))
    acceleration = _first_not_none(_k(cp, "a", "m/s^2"), pool.get("a"))
    if None in (m, force, acceleration):
        return []
    return [ResidualCheck("단일 질점: F - ma", force - m * acceleration, max(abs(force), abs(m * acceleration), 1.0))]


def _massive_pulley(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    m1, m2 = _k(cp, "m1", "kg"), _k(cp, "m2", "kg")
    inertia = _first_not_none(_k(cp, "I", "kg*m^2"), _k(cp, "Ip", "kg*m^2"))
    radius = _first_not_none(_k(cp, "R", "m"), _k(cp, "Rp", "m"))
    gravity, acceleration = _k(cp, "g", "m/s^2"), pool.get("a")
    if None in (m1, m2, inertia, radius, gravity, acceleration) or radius == 0:
        return []
    effective_mass = m1 + m2 + inertia / (radius * radius)
    drive = (m2 - m1) * gravity
    return [ResidualCheck("질량 도르래: (m2-m1)g - (m1+m2+I/R²)a", drive - effective_mass * acceleration, max(abs(drive), 1.0))]


def _vertical_circle(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    radius, gravity = _k(cp, "R", "m"), _k(cp, "g", "m/s^2")
    if radius is None or gravity is None:
        return []
    minimum_speed = pool.get("v_min")
    if minimum_speed is not None:
        expected = gravity * radius
        return [ResidualCheck("수직원 최고점 최소속도: v² - gR", minimum_speed * minimum_speed - expected, max(expected, 1.0))]
    tension, mass, speed = pool.get("T"), _k(cp, "m", "kg"), _k(cp, "v", "m/s")
    if None in (tension, mass, speed):
        return []
    if cp.subtype == "top":
        residual = tension + mass * gravity - mass * speed * speed / radius
        name = "수직원 최고점: T + mg - mv²/R"
    else:
        residual = tension - mass * gravity - mass * speed * speed / radius
        name = "수직원 최저점: T - mg - mv²/R"
    return [ResidualCheck(name, residual, max(abs(tension), mass * gravity, mass * speed * speed / radius, 1.0))]


def _instant_center(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    radius = _first_not_none(_k(cp, "r", "m"), _k(cp, "R", "m"))
    omega = _first_not_none(_k(cp, "omega", "rad/s"), pool.get("omega"))
    speed = _first_not_none(pool.get("v"), pool.get("v_B"))
    if None in (radius, omega, speed):
        return []
    expected = abs(omega) * radius
    return [ResidualCheck("순간중심 속력: v - |ω|r", speed - expected, max(abs(expected), 1.0))]


def _relative_translation(cp: CanonicalProblem, pool: dict) -> list[ResidualCheck]:
    aA = _k(cp, "aA", "m/s^2")
    arel = _k(cp, "arel", "m/s^2")
    aB = pool.get("a_B")
    if None in (aA, arel) or aB is None:
        return []
    compact = (cp.raw_text or "").lower().replace(" ", "")
    sign = -1.0 if ("반대방향" in compact or "opposite" in compact) else 1.0
    expected = aA + sign * arel
    operator = "-" if sign < 0 else "+"
    return [
        ResidualCheck(
            f"상대가속도 a_B - (a_A {operator} a_rel)",
            aB - expected,
            max(abs(expected), 1.0),
        )
    ]


CHECKERS: dict[str, Callable[[CanonicalProblem, dict], list[ResidualCheck]]] = {
    "single_particle_newton": _single_particle,
    "particle_on_incline": _incline,
    "pulley_atwood": _atwood,
    "pulley_table_hanging": _table_hanging,
    "pulley_incline_hanging": _incline_hanging,
    "massive_pulley_atwood": _massive_pulley,
    "projectile_motion": _projectile,
    "collision_1d": _collision,
    "constant_acceleration_1d": _const_acc,
    "work_energy_speed": _work_energy,
    "spring_energy": _spring_energy,
    "spring_mass_vibration": _spring_vibration,
    "constant_force_work": _const_force_work,
    "impulse_momentum": _impulse,
    "fixed_axis_rotation": _fixed_axis,
    "vertical_circle": _vertical_circle,
    "instant_center_velocity": _instant_center,
    "horizontal_friction_force": _horizontal_friction,
    "flat_curve_friction": _curve_flat,
    "banked_curve_no_friction": _curve_banked,
    "polar_kinematics": _polar,
    "slot_pin_relative_motion": _polar,
    "coriolis_relative_motion": _coriolis,
    "plane_rigid_body_velocity": _rigid_velocity,
    "plane_rigid_body_acceleration": _rigid_acceleration,
    "relative_acceleration_translation": _relative_translation,
}


# 각 유형의 답 계산에 실제로 쓰이는 known 심볼 (residual 검사기가 읽는 키에서 도출).
# provenance 정책에 사용: 배경 문장에서 주입된 값이 이 집합에 있으면 답 보류(error),
# 없으면 답 유지 + 주의(warning).
RELEVANT_KNOWNS: dict[str, set[str]] = {
    "single_particle_newton": {"m", "F", "a"},
    "particle_on_incline": {"g", "theta", "mu", "mu_k", "mu_s"},
    "pulley_atwood": {"g", "m1", "m2"},
    "pulley_table_hanging": {"g", "m1", "m2", "mu", "mu_k", "mu_s"},
    "pulley_incline_hanging": {"g", "m1", "m2", "theta", "mu", "mu_k", "mu_s"},
    "massive_pulley_atwood": {"g", "m1", "m2", "I", "Ip", "R", "Rp"},
    "projectile_motion": {"g", "v0", "v", "theta", "h"},
    "collision_1d": {"m1", "m2", "v1", "v2", "e"},
    "constant_acceleration_1d": {"v0", "vf", "a", "t", "s"},
    "work_energy_speed": {"m", "W", "F", "s", "v0"},
    "spring_energy": {"k", "m", "x", "A"},
    "spring_mass_vibration": {"k", "m"},
    "constant_force_work": {"F", "s", "theta"},
    "impulse_momentum": {"F", "t", "m", "v0"},
    "fixed_axis_rotation": {"tau", "I", "omega", "omega0", "alpha", "t"},
    "vertical_circle": {"m", "R", "v", "g"},
    "instant_center_velocity": {"r", "R", "omega", "v", "vB"},
    "horizontal_friction_force": {"mu", "mu_k", "m", "m1", "g"},
    "pure_rolling_energy": {"g", "h"},
    "rolling_energy_general": {"g", "h", "I", "R", "m"},
    "flat_curve_friction": {"g", "r", "R", "mu", "mu_k", "mu_s"},
    "banked_curve_no_friction": {"g", "r", "R", "theta"},
    "polar_kinematics": {"r", "R", "rdot", "rddot", "omega", "thetadot", "alpha", "thetaddot"},
    "slot_pin_relative_motion": {"r", "R", "rdot", "rddot", "omega", "alpha"},
    "coriolis_relative_motion": {"omega", "thetadot", "vrel", "rdot", "r", "R", "alpha", "thetaddot", "arel", "rddot"},
    "plane_rigid_body_velocity": {"omega", "r", "R", "vA", "vAx", "vAy", "rBAx", "rBAy"},
    "plane_rigid_body_acceleration": {"omega", "alpha", "r", "R", "aA", "aAx", "aAy", "rBAx", "rBAy"},
    "relative_acceleration_translation": {"aA", "arel"},
}


def _extract_beta(display: str | None) -> float | None:
    if not display:
        return None
    m = re.search(r"β\s*=\s*([0-9.]+)", display)
    return float(m.group(1)) if m else None


def run_residual_checks(cp: CanonicalProblem, pool: dict, rep_display: str | None = None) -> tuple[list[ResidualCheck], bool]:
    """(checks, supported). supported=False → 이 유형은 역대입 미지원(정직하게 보고)."""
    st = cp.system_type
    if st in ("pure_rolling_energy", "rolling_energy_general"):
        return _rolling(cp, pool, _extract_beta(rep_display)), True
    fn = CHECKERS.get(st)
    if fn is None:
        return [], False
    return fn(cp, pool), True
