from engine.models import CanonicalProblem


def analyze_student_solution(c: CanonicalProblem, student_solution: str) -> dict:
    s = student_solution.lower().replace(" ", "")
    good, missing, misconceptions, corrected = [], [], [], []

    if "f=ma" in s or "Σf" in student_solution or "sigma" in s:
        good.append("뉴턴 제2법칙을 떠올린 점은 좋습니다.")
    if "에너지" in student_solution or "mgh" in s:
        good.append("에너지 관점으로 접근하려 한 점은 좋습니다.")

    if c.system_type == "particle_on_incline":
        if "sin" not in s and "mg" in s:
            misconceptions.append("경사면 문제에서 중력 전체 mg를 운동방향 힘처럼 사용한 가능성이 있습니다.")
            missing.append("중력을 mg sinθ와 mg cosθ로 분해해야 합니다.")
        if c.subtype == "no_friction" and ("μ" in student_solution or "mu" in s or "마찰" in student_solution):
            misconceptions.append("마찰 없음 조건인데 마찰력을 식에 넣었습니다.")
        corrected.extend(["x축을 경사면 아래 방향으로 잡습니다.", "ΣF_x = ma", "마찰이 없으면 mg sinθ = ma", "따라서 a = g sinθ"])

    elif c.system_type == "pure_rolling_energy":
        if "1/2mv" in s and ("i" not in s and "ω" not in student_solution and "omega" not in s):
            missing.append("구름 운동에서는 병진 운동에너지뿐 아니라 회전 운동에너지도 필요합니다.")
        if c.flags.get("slipping") and ("v=wr" in s or "v=ωr" in student_solution):
            misconceptions.append("미끄러짐이 있으면 v=ωR을 바로 쓸 수 없습니다.")
        corrected.extend(["mgh = 1/2mv² + 1/2Iω²", "순수 구름이면 v=ωR", "강체의 관성모멘트를 확인합니다."])

    elif c.system_type == "vertical_circle":
        if "구심력" in student_solution and "=" in student_solution:
            misconceptions.append("구심력은 새 힘이 아니라 중심 방향 실제 힘들의 합입니다.")
        corrected.extend(["중심 방향을 +로 둡니다.", "최고점/최저점에 따라 힘의 부호를 정합니다.", "ΣF_n = mv²/R을 적용합니다."])

    elif c.system_type == "constant_acceleration_1d":
        if "s=vt" in s and "1/2" not in s and "가속" in c.raw_text:
            misconceptions.append("가속도가 있는데 등속도 공식 s=vt만 사용한 가능성이 있습니다.")
            missing.append("등가속도에서는 s=v0t+1/2at² 또는 vf²=v0²+2as 같은 식을 검토해야 합니다.")
        corrected.extend(["운동방향을 +로 정합니다.", "v0, vf, a, t, s 중 알려진 값을 정리합니다.", "등가속도 공식 4개 중 필요한 식을 고릅니다."])

    elif c.system_type == "projectile_motion":
        if "cos" not in s and "sin" not in s:
            missing.append("초속도를 수평/수직 성분으로 나누는 단계가 필요합니다.")
        corrected.extend(["v0x=v0cosθ, v0y=v0sinθ로 분해합니다.", "x방향은 등속도, y방향은 등가속도 운동으로 풉니다.", "착지 높이가 같은지 확인합니다."])

    elif c.system_type == "fixed_axis_rotation":
        if "f=ma" in s:
            misconceptions.append("고정축 회전 문제에서 병진식 F=ma만 사용했습니다. 회전식 ΣM=Iα가 필요합니다.")
        corrected.extend(["회전축을 정합니다.", "그 축에 대한 토크합을 구합니다.", "ΣM=Iα를 적용합니다."])

    if not good:
        good.append("문제 풀이를 시도한 점은 좋습니다. 이제 조건과 좌표축을 더 명확히 잡아보면 됩니다.")
    if not missing:
        missing.append("현재 자동 피드백 기준으로 큰 누락은 감지되지 않았습니다. 단, 최종 식과 단위 검산은 필요합니다.")
    if not corrected:
        corrected.append("문제 유형을 먼저 확정하고, FBD → 좌표축 → 운동방정식 → 검산 순서로 다시 정리하세요.")

    return {"good_points": good, "missing_points": missing, "misconceptions": misconceptions, "corrected_steps": corrected}
