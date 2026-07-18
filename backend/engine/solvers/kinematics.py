import math
from itertools import combinations

import sympy as sp
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.physics_core.units import magnitude_si
from engine.verification.checks import require_no_missing, merge_reports
from engine.physics_core.validators import (
    ValidationContext,
    VariableConstraint,
    candidate_from_mapping,
    validate_and_select,
)


class ConstantAcceleration1DSolver(BaseSolver):
    name = "constant_acceleration_1d"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "constant_acceleration_1d":
            return SolverMatch(self, 82, "등가속도 직선운동 공식 4개를 이용")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        # Phase 55 structured parses are authoritative. Legacy raw-text behavior
        # remains only for off/shadow rollback compatibility.
        structured = bool((c.textbook_parse or {}).get("authoritative"))
        raw = "" if structured else c.raw_text.replace(" ", "")
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
        starts_from_rest = bool(c.flags.get("starts_from_rest")) or any(
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
        ends_at_rest = bool(c.flags.get("ends_at_rest")) or any(
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
        if not structured and "v" in known and "v0" not in known and ("초속도" in raw or "처음" in raw):
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
            inconsistent = [
                str(eq)
                for eq in equations
                if not _residual_is_zero((eq.lhs - eq.rhs).subs(substitutions))
            ]
            if inconsistent:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=[
                            "주어진 v0, vf, a, t, s가 모든 등가속도 운동식을 동시에 만족하지 않습니다."
                        ],
                    ),
                    unsupported_reason="서로 모순되는 등가속도 조건을 확인해 주세요.",
                )
            return SolverResult(
                ok=True,
                answer=Answer(
                    symbolic="all constant-acceleration residuals = 0",
                    numeric=None,
                    unit="",
                    display="주어진 등가속도 조건은 서로 일치합니다.",
                ),
                steps=[
                    StepCard(
                        "조건 일관성 검사",
                        "다섯 변수가 모두 주어져 네 개의 독립 등가속도 운동식에 전부 대입했습니다.",
                    )
                ],
                verification=VerificationReport(
                    passed=True,
                    checks=["네 등가속도 운동식의 잔차가 모두 0입니다."],
                ),
                used_equations=["vf=v0+at", "s=v0t+1/2at²", "vf²=v0²+2as", "s=(v0+vf)t/2"],
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

        candidate_solutions = [
            candidate_from_mapping(
                state,
                candidate_id=f"kinematics-state-{index}",
                branch_info={"state_index": index, **branch_info},
                rank_metadata={"solver": self.name},
            )
            for index, (state, branch_info) in enumerate(states)
        ]
        preferred_candidate_id = None
        event_description = None
        if requested_keys == ["t"] and len(candidate_solutions) > 1:
            positive_time_candidates = [
                (candidate, value)
                for candidate in candidate_solutions
                if (
                    value := _finite_real_value(
                        candidate.symbolic_mapping.get(sym_map["t"])
                    )
                )
                is not None
                and value > 1e-9
            ]
            selected_time = _select_event_value(
                c,
                "t",
                [value for _, value in positive_time_candidates],
            )
            if selected_time is not None:
                for candidate, value in positive_time_candidates:
                    if math.isclose(
                        value,
                        selected_time,
                        rel_tol=1e-8,
                        abs_tol=1e-9,
                    ):
                        preferred_candidate_id = candidate.candidate_id
                        event_description = (
                            "문제의 처음/다시/진행 구간 표현이 시간 사건을 유일하게 지정했습니다."
                        )
                        break
        explicit_constraints = []
        if sym_map["t"] in [sym_map[key] for key in unknown_candidates]:
            explicit_constraints.append(
                VariableConstraint(
                    sym_map["t"],
                    lower_bound=0.0,
                    lower_inclusive=True,
                    reason="시간은 명시된 운동 구간에서 0 이상이어야 합니다.",
                    source="constant_acceleration_time_domain",
                )
            )
        candidate_context = ValidationContext(
            equations=equations,
            substitutions=substitutions,
            constraints=explicit_constraints,
            requested_symbols=[sym_map[key] for key in requested_keys],
            preferred_candidate_id=preferred_candidate_id,
            event_description=event_description,
            selection_policy="constant-acceleration-explicit-event",
        )
        selection_decision = validate_and_select(
            candidate_solutions,
            candidate_context,
        )
        if (
            selection_decision.status != "selected"
            or selection_decision.selected_candidate is None
        ):
            if selection_decision.status == "ambiguous":
                alternatives = ", ".join(
                    str(candidate.numerical_mapping)
                    for candidate in selection_decision.valid_alternatives
                )
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        warnings=[
                            "물리적으로 가능한 등가속도 후보가 여러 개입니다: "
                            + alternatives
                        ],
                    ),
                    unsupported_reason=(
                        "운동의 시간 구간이나 진행 방향을 더 지정해 어떤 해인지 선택해 주세요."
                    ),
                    selection_decision=selection_decision,
                )
            has_failed_equation_residual = (
                selection_decision.status == "no_valid_solution"
                and any(
                    check.category == "equation_residual"
                    and check.status == "failed"
                    for rejected in selection_decision.rejected_candidates
                    for check in rejected.checks
                )
            )
            error_prefix = (
                "입력한 등가속도 조건 사이의 모순으로 "
                if has_failed_equation_residual
                else ""
            )
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=[
                        error_prefix
                        + "공통 후보 검증에서 등가속도 해를 확정하지 못했습니다: "
                        + selection_decision.status
                    ],
                ),
                unsupported_reason=(
                    "입력한 등가속도 조건 사이의 모순을 확인해 주세요."
                    if has_failed_equation_residual
                    else "입력한 조건과 물리적 정의역을 확인해 주세요."
                ),
                selection_decision=selection_decision,
            )

        selected_state = selection_decision.selected_candidate.symbolic_mapping
        solved: list[tuple[str, float]] = [
            (key, float(selected_state[sym_map[key]]))
            for key in requested_keys
            if sym_map[key] in selected_state
        ]

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
            selection_decision=selection_decision,
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


def _select_event_value(c: CanonicalProblem, key: str, values: list[float]) -> float | None:
    """Select a root only when the problem states which event is intended."""

    if key != "t" or not values:
        return None
    positive = [value for value in values if value > 1e-9]
    if (c.textbook_parse or {}).get("authoritative"):
        selection = (c.textbook_parse.get("event_selection") or {}).get("time")
        if selection == "last":
            return max(positive or values)
        if selection == "first":
            return min(positive or values)
        return None
    raw = (c.raw_text or "").lower().replace(" ", "")

    later_tokens = (
        "다시",
        "재차",
        "돌아오",
        "되돌아오",
        "두번째",
        "두번째",
        "꼭대기이후",
        "내려오",
        "하강하며",
    )
    if any(token in raw for token in later_tokens):
        return max(positive or values)

    first_tokens = (
        "처음으로",
        "최초",
        "첫번째",
        "첫번째",
        "올라가며",
        "상승하며",
    )
    if any(token in raw for token in first_tokens):
        return min(positive or values)

    if any(token in raw for token in ("t>0", "t＞0", "0보다큰시간", "출발후")):
        return positive[0] if len(positive) == 1 else None
    return None


def _finite_real_value(value) -> float | None:
    if value is None:
        return None
    try:
        evaluated = sp.N(value)
        if getattr(evaluated, "free_symbols", set()):
            return None
        numeric = complex(evaluated)
    except Exception:
        return None
    if abs(numeric.imag) > 1e-9 or not math.isfinite(numeric.real):
        return None
    return float(numeric.real)


def _consistent_states(equations, substitutions, sym_map, unknown_candidates: list[str]):
    unknown_symbols = [sym_map[key] for key in unknown_candidates]
    solve_symbols = [
        sp.Dummy(f"{symbol}_candidate") for symbol in unknown_symbols
    ]
    to_unconstrained = dict(zip(unknown_symbols, solve_symbols))
    from_unconstrained = dict(zip(solve_symbols, unknown_symbols))
    residuals = [(eq.lhs - eq.rhs).subs(substitutions) for eq in equations]

    active = [
        residual
        for residual in residuals
        if any(symbol in residual.free_symbols for symbol in unknown_symbols)
    ]
    raw_solutions: list[tuple[dict, int, int]] = []
    solve_sets = [active]
    if len(active) >= len(unknown_symbols):
        solve_sets.extend(
            list(group)
            for group in combinations(active, len(unknown_symbols))
        )

    for solve_set_index, equation_set in enumerate(solve_sets):
        try:
            solved_set = sp.solve(
                [equation.xreplace(to_unconstrained) for equation in equation_set],
                solve_symbols,
                dict=True,
            )
        except Exception:
            continue
        normalized_solutions = [
            {
                original_symbol: sp.sympify(solution[solve_symbol]).xreplace(
                    from_unconstrained
                )
                for original_symbol, solve_symbol in zip(
                    unknown_symbols, solve_symbols
                )
                if solve_symbol in solution
            }
            for solution in solved_set
        ]
        raw_solutions.extend(
            (dict(solution), solve_set_index, solution_index)
            for solution_index, solution in enumerate(normalized_solutions)
        )
        # The full active system is authoritative when it yields branches.
        # If it is empty, every fallback subsystem must run: an early partial
        # mapping is unvalidated and cannot suppress a later complete branch.
        if solve_set_index == 0 and solved_set:
            break

    states: list[tuple[dict, dict]] = []
    seen_mappings: set[tuple[tuple[str, str], ...]] = set()
    for raw_solution_index, (
        solution,
        solve_set_index,
        solve_set_solution_index,
    ) in enumerate(raw_solutions):
        state = {
            symbol: solution.get(symbol, symbol)
            for symbol in unknown_symbols
        }
        try:
            mapping_identity = tuple(
                (sp.srepr(symbol), sp.srepr(sp.sympify(state[symbol])))
                for symbol in unknown_symbols
            )
        except Exception:
            mapping_identity = tuple(
                (str(symbol), repr(state[symbol]))
                for symbol in unknown_symbols
            )
        if mapping_identity in seen_mappings:
            continue
        seen_mappings.add(mapping_identity)
        states.append(
            (
                state,
                {
                    "raw_solution_index": raw_solution_index,
                    "solve_set_index": solve_set_index,
                    "solve_set_solution_index": solve_set_solution_index,
                    "raw_mapping": {
                        str(symbol): str(value)
                        for symbol, value in solution.items()
                    },
                },
            )
        )

    return states, None


def _residual_is_zero(residual) -> bool:
    try:
        value = complex(sp.N(residual))
    except Exception:
        return False
    if abs(value.imag) > 1e-9:
        return False
    return abs(value.real) <= 1e-7


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

    if (c.textbook_parse or {}).get("authoritative"):
        return candidates[0]

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
