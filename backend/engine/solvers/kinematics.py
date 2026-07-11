import math
from itertools import combinations

import sympy as sp
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.physics_core.units import magnitude_si
from engine.verification.checks import require_no_missing, merge_reports


class ConstantAcceleration1DSolver(BaseSolver):
    name = "constant_acceleration_1d"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "constant_acceleration_1d":
            return SolverMatch(self, 82, "등가속도 직선운동 공식 4개를 이용")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        raw = c.raw_text.replace(" ", "")
        unit_by_key = {
            "v0": "m/s",
            "vf": "m/s",
            "v": "m/s",
            "a": "m/s^2",
            "t": "s",
            "s": "m",
        }
        known = {}
        try:
            for key, quantity in c.knowns.items():
                if quantity.value is None:
                    continue
                known[key] = (
                    magnitude_si(quantity, unit_by_key[key])
                    if key in unit_by_key
                    else float(quantity.value)
                )
        except Exception as exc:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=[f"등가속도 입력 단위를 변환하지 못했습니다: {exc}"],
                ),
            )

        compact_lower = raw.lower()
        starts_from_rest = any(
            phrase in compact_lower
            for phrase in (
                "정지상태에서",
                "정지상태로부터",
                "정지에서",
                "처음에는정지",
                "초기에는정지",
                "처음에정지한",
                "정지한물체",
                "startsfromrest",
                "initiallyatrest",
            )
        )
        ends_at_rest = any(
            phrase in compact_lower
            for phrase in (
                "정지할때",
                "정지할때까지",
                "마지막에정지",
                "최종적으로정지",
                "멈출때",
                "comestorest",
                "stopsafter",
            )
        )
        if starts_from_rest:
            known.setdefault("v0", 0.0)
        if ends_at_rest:
            known.setdefault("vf", 0.0)
        if "v" in known and "v0" not in known and ("초속도" in raw or "처음" in raw):
            known["v0"] = known["v"]
        pre = require_no_missing(c)
        # 정지 보완 때문에 missing을 다시 판단
        if len({"v0", "vf", "a", "t", "s"}.intersection(known.keys())) < 3:
            return SolverResult(
                ok=False,
                verification=VerificationReport(passed=False, errors=["등가속도 운동은 v0, vf, a, t, s 중 최소 3개가 필요합니다."]),
                unsupported_reason="정보가 부족합니다. 예: 초속도 0m/s, 가속도 2m/s², 시간 5s, 최종속도?",
            )

        v0, vf, a, t, s = sp.symbols("v0 vf a t s", real=True)
        sym_map = {"v0": v0, "vf": vf, "a": a, "t": t, "s": s}
        equations = [
            sp.Eq(vf, v0 + a * t),
            sp.Eq(s, v0 * t + sp.Rational(1, 2) * a * t**2),
            sp.Eq(vf**2, v0**2 + 2 * a * s),
            sp.Eq(s, sp.Rational(1, 2) * (v0 + vf) * t),
        ]
        substitutions = {sym_map[k]: float(v) for k, v in known.items() if k in sym_map}
        unknown_candidates = [k for k in ["vf", "s", "t", "a", "v0"] if k not in known]

        if not unknown_candidates:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["모든 등가속도 변수가 이미 주어져 있어 새로 계산할 미지수가 없습니다."],
                ),
                unsupported_reason="구하려는 값을 하나 이상 미지수로 남겨 주세요.",
            )
        requested_keys = _requested_keys(c, unknown_candidates)

        if "t" in known and float(known["t"]) < -1e-9:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["시간 t는 0 이상이어야 합니다."],
                ),
            )

        states, state_error = _consistent_states(
            equations,
            substitutions,
            sym_map,
            unknown_candidates,
        )
        if not states:
            underdetermined = bool(state_error and "유일" in state_error)
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=[state_error or "주어진 값들이 네 등가속도 운동식과 동시에 양립하지 않습니다."],
                ),
                unsupported_reason=(
                    "미지수를 유일하게 정하려면 독립적인 운동 조건을 하나 더 알려 주세요."
                    if underdetermined
                    else "입력한 v0, vf, a, t, s 중 서로 모순되는 값을 확인해 주세요."
                ),
            )

        solved: list[tuple[str, float]] = []
        for requested in requested_keys:
            values = _unique_values(float(state[sym_map[requested]]) for state in states)
            if len(values) > 1:
                formatted = ", ".join(f"{value:.6g}" for value in values)
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        warnings=[
                            f"{_label_for(requested)}에 물리적으로 가능한 해가 여러 개입니다: {formatted} {_unit_for(requested)}"
                        ],
                        errors=[],
                    ),
                    unsupported_reason="운동의 시간 구간이나 진행 방향을 더 지정해 어떤 해인지 선택해 주세요.",
                )
            if values:
                solved.append((requested, values[0]))

        if not solved:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["요청한 미지수를 일관된 등가속도 상태에서 계산하지 못했습니다."],
                ),
            )

        answers: list[AnswerItem] = []
        for key, value in solved:
            unit = _unit_for(key)
            label = _label_for(key)
            answers.append(AnswerItem(label=label, symbol=key, numeric=round(value, 6), unit=unit, display=f"{label} {key} = {value:.3f} {unit}", role="primary"))

        first_key, first_value = solved[0]
        first_unit = _unit_for(first_key)
        first_label = _label_for(first_key)
        if len(solved) == 1:
            result_display = f"{first_label} = {first_value:.3f} {first_unit}"
        else:
            result_display = ", ".join(a.display for a in answers)

        steps = [
            StepCard("문제 유형", "가속도가 일정한 직선 운동이므로 등가속도 운동 공식들을 사용합니다."),
            StepCard("변수 정리", f"알고 있는 값: {', '.join(sorted(k for k in known if k in sym_map))}. 구할 값: {', '.join(_label_for(k) for k, _ in solved)}."),
            StepCard("대표 공식", "필요한 값 조합에 맞춰 아래 네 공식 중 하나를 사용합니다.", r"v_f=v_0+at,\quad s=v_0t+\frac12at^2,\quad v_f^2=v_0^2+2as"),
            StepCard("계산 결과", "; ".join(f"{_label_for(k)} = {v:.5g} {_unit_for(k)}" for k, v in solved)),
        ]
        checks = [
            "등가속도 공식은 가속도가 일정할 때만 사용합니다.",
            "시간 t가 음수로 나오면 물리적으로 잘못된 해이므로 제외했습니다.",
        ]
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="constant-acceleration equations", numeric=round(first_value, 5), unit=first_unit, display=result_display),
            answers=answers,
            steps=steps,
            verification=merge_reports(pre if pre.passed else VerificationReport(passed=True), VerificationReport(passed=True, checks=checks)),
            used_equations=["vf=v0+at", "s=v0t+1/2at²", "vf²=v0²+2as", "s=(v0+vf)t/2"],
            coordinate_guide=["운동 방향을 +x로 잡고 속도와 가속도 부호를 정합니다."],
        )


def _requested_keys(c: CanonicalProblem, candidates: list[str]) -> list[str]:
    requested_map = {
        "time": "t",
        "distance": "s",
        "range": "s",
        "final_velocity": "vf",
        "acceleration": "a",
        "initial_velocity": "v0",
    }
    keys: list[str] = []
    for req in (c.requested_outputs or c.unknowns or []):
        target = requested_map.get(req)
        if target in candidates and target not in keys:
            keys.append(target)
    if keys:
        return keys
    return [_requested_key(c, candidates)]


def _consistent_states(equations, substitutions, sym_map, unknown_candidates: list[str]):
    unknown_symbols = [sym_map[key] for key in unknown_candidates]
    residuals = [(eq.lhs - eq.rhs).subs(substitutions) for eq in equations]

    for residual in residuals:
        if not residual.free_symbols and not _residual_is_zero(residual):
            return [], "주어진 값들만 대입해도 등가속도 운동식 사이에 모순이 생깁니다."

    active = [
        residual
        for residual in residuals
        if any(symbol in residual.free_symbols for symbol in unknown_symbols)
    ]
    raw_solutions: list[dict] = []
    solve_sets = [active]
    if len(active) >= len(unknown_symbols):
        solve_sets.extend(
            list(group)
            for group in combinations(active, len(unknown_symbols))
        )

    for equation_set in solve_sets:
        try:
            raw_solutions.extend(
                sp.solve(equation_set, unknown_symbols, dict=True)
            )
        except Exception:
            continue

    states: list[dict] = []
    underdetermined = False
    for solution in raw_solutions:
        if any(symbol not in solution for symbol in unknown_symbols):
            underdetermined = True
            continue
        state: dict = {}
        valid = True
        for symbol in unknown_symbols:
            value = sp.N(solution[symbol])
            if value.free_symbols:
                valid = False
                break
            complex_value = complex(value)
            if abs(complex_value.imag) > 1e-9 or not math.isfinite(complex_value.real):
                valid = False
                break
            state[symbol] = float(complex_value.real)
        if not valid:
            continue
        t_symbol = sym_map.get("t")
        if t_symbol is not None:
            time_value = state.get(t_symbol, substitutions.get(t_symbol))
            if time_value is not None and float(time_value) < -1e-9:
                continue
        if not all(_equation_is_satisfied(eq, substitutions, state) for eq in equations):
            continue
        if not any(_same_state(state, existing, unknown_symbols) for existing in states):
            states.append(state)

    if not states and underdetermined:
        return [], "주어진 조건만으로는 미지수가 유일하게 결정되지 않습니다."
    return states, None


def _residual_is_zero(residual) -> bool:
    try:
        value = complex(sp.N(residual))
    except Exception:
        return False
    if abs(value.imag) > 1e-9:
        return False
    return abs(value.real) <= 1e-7


def _equation_is_satisfied(eq, substitutions, state) -> bool:
    try:
        lhs = complex(sp.N(eq.lhs.subs(substitutions).subs(state)))
        rhs = complex(sp.N(eq.rhs.subs(substitutions).subs(state)))
    except Exception:
        return False
    if abs(lhs.imag) > 1e-9 or abs(rhs.imag) > 1e-9:
        return False
    scale = max(abs(lhs.real), abs(rhs.real), 1.0)
    return abs(lhs.real - rhs.real) <= 1e-7 * scale


def _same_state(left: dict, right: dict, symbols: list) -> bool:
    return all(
        math.isclose(float(left[symbol]), float(right[symbol]), rel_tol=1e-8, abs_tol=1e-9)
        for symbol in symbols
    )


def _unique_values(values) -> list[float]:
    unique: list[float] = []
    for value in values:
        if not any(math.isclose(value, seen, rel_tol=1e-8, abs_tol=1e-9) for seen in unique):
            unique.append(value)
    return sorted(unique)


def _requested_key(c: CanonicalProblem, candidates: list[str]) -> str:
    requested_map = {
        "time": "t",
        "distance": "s",
        "range": "s",
        "final_velocity": "vf",
        "acceleration": "a",
        "initial_velocity": "v0",
    }
    for req in c.requested_outputs or []:
        target = requested_map.get(req)
        if target in candidates:
            return target

    raw = c.raw_text.replace(" ", "")
    # 한국어 문장에서는 이미 주어진 값 이름도 본문에 함께 나오므로,
    # "구하라/얼마/걸리는" 근처 표현을 먼저 본다.
    if any(x in raw for x in ["걸리는시간", "소요시간", "시간을구", "시간은", "몇초"]):
        return "t" if "t" in candidates else candidates[0]
    if any(x in raw for x in ["이동거리", "이동한거리", "변위를구", "거리를구", "거리은", "거리는"]):
        return "s" if "s" in candidates else candidates[0]
    if any(x in raw for x in ["최종속도", "나중속도", "속도를구", "속도는"]):
        return "vf" if "vf" in candidates else candidates[0]
    if any(x in raw for x in ["초속도", "처음속도"]):
        return "v0" if "v0" in candidates else candidates[0]
    if any(x in raw for x in ["가속도를구", "가속도는"]):
        return "a" if "a" in candidates else candidates[0]
    if "시간" in raw or "몇초" in raw:
        return "t" if "t" in candidates else candidates[0]
    if "거리" in raw or "변위" in raw:
        return "s" if "s" in candidates else candidates[0]
    if "가속도" in raw:
        return "a" if "a" in candidates else candidates[0]
    return candidates[0]


def _unit_for(key: str) -> str:
    return {"vf": "m/s", "v0": "m/s", "a": "m/s²", "t": "s", "s": "m"}[key]


def _label_for(key: str) -> str:
    return {"vf": "최종속도", "v0": "초속도", "a": "가속도", "t": "시간", "s": "변위/거리"}[key]
