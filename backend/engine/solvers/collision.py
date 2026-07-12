from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.equation_generators.energy_momentum import solve_energy_momentum_system
from engine.model_builder import build_physical_model
from engine.model_builder.model_types import PhysicalModel


def _invalid_collision_result(message: str) -> SolverResult:
    return SolverResult(
        ok=False,
        verification=VerificationReport(passed=False, errors=[message]),
        unsupported_reason="충돌 조건과 반발계수/충돌 유형을 확인해 주세요.",
    )


class Collision1DSolver(BaseSolver):
    uses_prebuilt_physical_model = True
    name = "collision_1d"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "collision_1d":
            return SolverMatch(self, 74, "1차원 충돌: 운동량 보존 + 조건식")
        return None

    def solve(self, c: CanonicalProblem, model: PhysicalModel | None = None) -> SolverResult:
        m1 = c.knowns.get("m1")
        m2 = c.knowns.get("m2")
        v1q = c.knowns.get("v1")
        v2q = c.knowns.get("v2")
        if not (m1 and m2 and v1q and v2q):
            return SolverResult(
                ok=False,
                verification=VerificationReport(passed=False, errors=["m1, m2, v1, v2가 필요합니다. 예: m1=2kg, m2=3kg, v1=4m/s, v2=0m/s"]),
                unsupported_reason="충돌 solver는 명시적 m1, m2, v1, v2 형식을 권장합니다.",
            )
        M1, M2, v1, v2 = float(m1.value), float(m2.value), float(v1q.value), float(v2q.value)
        if M1 <= 0 or M2 <= 0:
            return _invalid_collision_result("두 질량 m1, m2는 0보다 커야 합니다.")
        # 이 1D solver의 좌표 계약은 body 1이 왼쪽에서 body 2를 따라잡는 경우다.
        # 위치/기하 정보가 없는 상태에서 v1<=v2이면 접근 중인 충돌이라고 단정할 수 없다.
        if v1 <= v2:
            return _invalid_collision_result(
                "현재 1D 라벨/축 계약에서 접근 상대속도 v1-v2가 양수여야 합니다. 두 물체의 위치 순서와 운동 방향을 알려 주세요."
            )

        elastic = bool((c.flags or {}).get("elastic"))
        perfectly_inelastic = bool((c.flags or {}).get("perfectly_inelastic"))
        eq = c.knowns.get("e")
        explicit_e = float(eq.value) if eq is not None and eq.value is not None else None
        if explicit_e is not None and not 0.0 <= explicit_e <= 1.0:
            return _invalid_collision_result("일반 충돌 모드의 반발계수는 0≤e≤1이어야 합니다.")
        if elastic and perfectly_inelastic:
            return _invalid_collision_result("완전탄성과 완전비탄성 조건이 동시에 주어졌습니다.")
        if elastic and explicit_e is not None and abs(explicit_e - 1.0) > 1e-12:
            return _invalid_collision_result("완전탄성 서술은 e=1과 모순됩니다.")
        if perfectly_inelastic and explicit_e is not None and abs(explicit_e) > 1e-12:
            return _invalid_collision_result("완전비탄성 서술은 e=0과 모순됩니다.")

        model = model or build_physical_model(c)
        generated = solve_energy_momentum_system(c, model)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, warnings=generated.errors, checks=["충돌 문제는 운동량 보존식 하나만으로는 보통 미지수가 2개라 부족합니다."]), unsupported_reason="완전비탄성 조건을 포함하거나 e 값을 입력하세요.")
        if c.flags.get("perfectly_inelastic"):
            vf = float(generated.solution["v_f"])
            steps = [
                StepCard("충돌 유형", "완전비탄성 충돌은 두 물체가 붙어서 같은 속도로 움직입니다."),
                StepCard("운동량 보존", "Energy/Momentum generator가 충돌선 방향 운동량 보존식을 생성합니다.", "m_1v_1 + m_2v_2 = (m_1+m_2)v_f"),
                StepCard("계산", f"v_f = ({M1:g}×{v1:g}+{M2:g}×{v2:g})/({M1:g}+{M2:g}) = {vf:.5g} m/s"),
            ]
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="vf=(m1v1+m2v2)/(m1+m2)", numeric=round(vf, 5), unit="m/s", display=f"v_f = {vf:.3f} m/s"),
                answers=[AnswerItem("충돌 후 공통 속도", "v_f", round(vf, 6), "m/s", f"충돌 후 공통 속도 v_f = {vf:.3f} m/s", "primary")],
                steps=steps,
                verification=VerificationReport(passed=True, checks=["완전비탄성에서는 운동에너지가 보존되지 않아도 됩니다."]),
            )

        e = 1.0 if elastic else explicit_e
        if e is not None:
            # 운동량 보존 + 반발계수: v2' - v1' = e(v1-v2)
            v1p = float(generated.solution["v1f"])
            v2p = float(generated.solution["v2f"])
            condition = "완전탄성(e=1)" if e == 1 else f"반발계수 e={e:g}"
            steps = [
                StepCard("충돌 유형", f"{condition} 조건을 사용합니다."),
                StepCard("운동량 보존", "Energy/Momentum generator가 충돌선 방향 운동량 보존식을 생성합니다.", "m_1v_1+m_2v_2=m_1v_1'+m_2v_2'"),
                StepCard("반발계수", "분리 상대속도 / 접근 상대속도 = e 입니다.", "v_2'-v_1'=e(v_1-v_2)"),
                StepCard("계산", f"v1'={v1p:.5g} m/s, v2'={v2p:.5g} m/s"),
            ]
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="v1', v2' from momentum + restitution", numeric=None, unit="m/s", display=f"v1' = {v1p:.3f} m/s, v2' = {v2p:.3f} m/s"),
                answers=[
                    AnswerItem("충돌 후 m1 속도", "v1'", round(v1p, 6), "m/s", f"충돌 후 m1의 속도 v1' = {v1p:.3f} m/s", "primary"),
                    AnswerItem("충돌 후 m2 속도", "v2'", round(v2p, 6), "m/s", f"충돌 후 m2의 속도 v2' = {v2p:.3f} m/s", "primary"),
                ],
                steps=steps,
                verification=VerificationReport(passed=True, checks=["e=1이면 완전탄성, e=0이면 완전비탄성에 가까운 조건입니다.", "속도는 방향을 포함한 부호 있는 값입니다."]),
            )

        return SolverResult(
            ok=False,
            verification=VerificationReport(passed=False, warnings=["완전비탄성/완전탄성/반발계수 e 중 하나가 필요합니다."], checks=["충돌 문제는 운동량 보존식 하나만으로는 보통 미지수가 2개라 부족합니다."]),
            unsupported_reason="완전비탄성 조건을 포함하거나 e 값을 입력하세요.",
        )
