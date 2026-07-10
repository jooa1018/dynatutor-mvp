import sympy as sp
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import require_no_missing, merge_reports


class ConstantAcceleration1DSolver(BaseSolver):
    name = "constant_acceleration_1d"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "constant_acceleration_1d":
            return SolverMatch(self, 82, "등가속도 직선운동 공식 4개를 이용")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        # 정지에서 출발 표현을 v0=0으로 보완
        raw = c.raw_text.replace(" ", "")
        known = {k: q.value for k, q in c.knowns.items() if q.value is not None}
        if "정지" in raw or "rest" in raw.lower():
            known.setdefault("v0", 0.0)
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
        requested_keys = _requested_keys(c, unknown_candidates)

        solved: list[tuple[str, float]] = []
        for requested in requested_keys:
            value = _solve_target(requested, equations, substitutions, sym_map, unknown_candidates)
            if value is not None:
                solved.append((requested, value))

        if not solved:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["현재 입력 조합으로는 등가속도 식을 안정적으로 풀지 못했습니다."]))

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
    for req in c.requested_outputs or []:
        target = requested_map.get(req)
        if target in candidates and target not in keys:
            keys.append(target)
    if keys:
        return keys
    return [_requested_key(c, candidates)]


def _solve_target(requested: str, equations, substitutions, sym_map, unknown_candidates: list[str]) -> float | None:
    target = sym_map[requested]
    reduced = [eq.subs(substitutions) for eq in equations]
    solutions: list[float] = []
    for eq in reduced:
        try:
            sols = sp.solve(eq, target)
            for sol in sols:
                if sol.is_real is False:
                    continue
                val = float(sol)
                if requested == "t" and val < -1e-9:
                    continue
                solutions.append(val)
        except Exception:
            pass
    if not solutions:
        # 연립방정식으로 재시도. 목표 변수가 포함되도록 미지수 순서를 구성합니다.
        try:
            ordered_unknowns = [requested] + [x for x in unknown_candidates if x != requested]
            eqs = [eq.subs(substitutions) for eq in equations[:2]]
            sols = sp.solve(eqs, [sym_map[x] for x in ordered_unknowns[:2]], dict=True)
            if sols and target in sols[0]:
                solutions.append(float(sols[0][target]))
        except Exception:
            pass
    if not solutions:
        return None
    return _choose_solution(solutions, requested)


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


def _choose_solution(values: list[float], requested: str) -> float:
    # 시간은 양수 해를 우선, 나머지는 절댓값이 작은 해를 우선한다.
    if requested == "t":
        positives = [v for v in values if v >= -1e-9]
        return min(positives) if positives else values[0]
    return min(values, key=lambda x: abs(x))


def _unit_for(key: str) -> str:
    return {"vf": "m/s", "v0": "m/s", "a": "m/s²", "t": "s", "s": "m"}[key]


def _label_for(key: str) -> str:
    return {"vf": "최종속도", "v0": "초속도", "a": "가속도", "t": "시간", "s": "변위/거리"}[key]
