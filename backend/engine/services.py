from app.schemas.solution import (
    ClarificationModel,
    ClarificationOptionModel,
    AnswerModel,
    AnswerItemModel,
    CanonicalProblemModel,
    DiagnosisResponse,
    FeedbackResponse,
    LegacyHintModel,
    QuantityModel,
    RouteCandidateModel,
    RouteDecisionModel,
    SolveResponse,
    StepCard as StepCardSchema,
    VerificationReport as VerificationReportSchema,
)
from engine.extraction.extractor import extract_problem
from engine.models import SolverResult, VerificationReport
from engine.legacy_hints.rules import make_legacy_hints
from engine.model_builder import build_physical_model, physical_model_step_cards
from engine.solvers.registry import SolverRegistry
from engine.tutor_cards import build_diagnosis_cards
from engine.feedback import analyze_student_solution
from engine.explanation import build_common_mistakes, build_concept_summary, build_equation_sheet, build_study_tips, build_teacher_summary
from engine.visualization.fbd import build_fbd_annotations, build_fbd_svg
from engine.physics_core.answer_validators import validate_solve_response
from engine.verification.suite import verify_result
from engine.verification.gate import apply_result_gate
from engine.routing.clarify import ClarifyPatchError, apply_clarify_patch, build_clarification, validate_clarify_patch
from engine.verification.checks import merge_reports
from engine.verification.plausibility import check_knowns



def _partial_guidance_steps(c):
    """실패/되묻기 응답에서도 '현재 알 수 있는 것'과 '추가 조건'을 분리해 보여준다."""
    possible: list[str] = []
    needed: list[str] = list(c.missing_info or [])
    st = c.system_type
    k = c.knowns or {}
    if st == "projectile_motion":
        if "h" in k or c.launch_height is not None:
            possible.append("높이 정보가 있으므로 수직방향 낙하/비행시간 식은 세울 수 있습니다.")
        if "v0" not in k and "v" not in k:
            needed.append("수평거리/사거리를 구하려면 초기 속도 또는 수평 속도 성분이 필요합니다.")
    elif st in ("constant_force_work", "work_energy_speed"):
        if "F" in k and "s" in k:
            possible.append("힘과 이동거리가 있으므로 W = Fs cosθ 식까지는 세울 수 있습니다.")
            if "theta" not in k:
                needed.append("힘과 변위 사이 각도 θ 또는 방향 관계")
    elif st == "particle_on_incline":
        possible.append("경사면 방향으로 중력 성분 mg sinθ를 쓰는 모델입니다.")
        if c.subtype == "unknown_friction":
            needed.append("마찰이 없으면 a=g sinθ, 마찰이 있으면 μg cosθ 항이 추가됩니다.")
    elif st == "pulley_table_hanging":
        if "m1" in k and "m2" in k:
            possible.append("수평면 위 m1과 매달린 m2가 같은 크기의 가속도를 갖는 구조까지는 확인됩니다.")
        if c.friction_type is None:
            needed.append("수평면 마찰 유무 또는 마찰계수 μ")
    elif st in ("flat_curve_friction", "banked_curve_no_friction", "vertical_circle"):
        possible.append("원운동 문제이므로 필요한 경우 a_c = v²/r 관계를 사용합니다.")
        if "R" not in k and "r" not in k:
            needed.append("반지름 r")
        if "v" not in k and "minimum_speed" not in c.unknowns:
            needed.append("속도 v 또는 구하려는 속도 조건")
    if not possible and k:
        possible.append("추출된 물리량은 '앱이 이해한 조건' 카드에서 확인하고 수정할 수 있습니다.")
    steps = []
    if possible:
        steps.append(StepCardSchema(title="현재 정보로 가능한 것", body="\n".join(f"- {x}" for x in dict.fromkeys(possible))))
    if needed:
        steps.append(StepCardSchema(title="추가로 필요한 조건", body="\n".join(f"- {x}" for x in dict.fromkeys(needed))))
    return steps


def _answer_item_model(a):
    return AnswerItemModel(label=a.label, symbol=a.symbol, numeric=a.numeric, unit=a.unit, display=a.display, role=a.role)


def _answers_from_result(result):
    if result.answers:
        return [_answer_item_model(a) for a in result.answers]
    if result.answer:
        label = "최종 답"
        return [AnswerItemModel(label=label, symbol=None, numeric=result.answer.numeric, unit=result.answer.unit, display=result.answer.display or "", role="primary")]
    return []

def _quantity_model(q):
    return QuantityModel(symbol=q.symbol, value=q.value, unit=q.unit, source_text=q.source_text)


def _canonical_model(c):
    return CanonicalProblemModel(
        system_type=c.system_type,
        subtype=c.subtype,
        language=c.language,
        objects=c.objects,
        knowns={k: _quantity_model(v) for k, v in c.knowns.items()},
        unknowns=c.unknowns,
        flags=c.flags,
        assumptions=c.assumptions,
        missing_info=c.missing_info,
        confidence=c.confidence,
        surface_type=c.surface_type,
        pulley_topology=c.pulley_topology,
        friction_type=c.friction_type,
        body_shape=c.body_shape,
        launch_height=c.launch_height,
        landing_height=c.landing_height,
        force_direction=c.force_direction,
        displacement_direction=c.displacement_direction,
        coordinate_data=c.coordinate_data,
        requested_outputs=c.requested_outputs,
        launch_angle_deg=c.launch_angle_deg,
        launch_angle_source=c.launch_angle_source,
    )


def _route_decision_model(decision):
    if decision is None:
        return None
    return RouteDecisionModel(
        status=decision.status,
        candidates=[
            RouteCandidateModel(
                solver_id=candidate.solver_id,
                family=candidate.family,
                raw_score=candidate.raw_score,
                normalized_score=candidate.normalized_score,
                evidence=candidate.evidence,
                missing_requirements=candidate.missing_requirements,
                contradictions=candidate.contradictions,
                supported_outputs=candidate.supported_outputs,
                risk_flags=candidate.risk_flags,
                source_system_type=candidate.source_system_type,
                source_subtype=candidate.source_subtype,
                interpretation_score=candidate.interpretation_score,
                interpretation_provenance=candidate.interpretation_provenance,
                selection_eligible=candidate.selection_eligible,
            )
            for candidate in decision.candidates
        ],
        selected_solver_id=decision.selected_solver_id,
        question=decision.question,
        reason=decision.reason,
        warnings=decision.warnings,
    )


def _physical_model_payload(payload, decision):
    out = dict(payload or {})
    route_model = _route_decision_model(decision)
    if route_model is not None:
        out["route_decision"] = route_model.model_dump()
    return out


def _route_clarification_model(decision, canonical):
    if decision is None or decision.status != "clarify" or not decision.question:
        return None
    options = []
    seen = set()
    current = (canonical.system_type, canonical.subtype)
    for candidate in decision.candidates:
        if "interpretation_variant" not in candidate.risk_flags:
            continue
        key = (candidate.source_system_type, candidate.source_subtype)
        if candidate.source_system_type is None or key in seen or key == current:
            continue
        patch = {
            "system_type": candidate.source_system_type,
            "subtype": candidate.source_subtype,
        }
        try:
            validate_clarify_patch(canonical, patch)
        except ClarifyPatchError:
            continue
        seen.add(key)
        subtype_id = candidate.source_subtype or "default"
        options.append(
            ClarificationOptionModel(
                id=f"route_{candidate.solver_id}_{candidate.source_system_type}_{subtype_id}",
                label=candidate.solver_id,
                description="; ".join(candidate.evidence),
                patch=patch,
            )
        )
        if len(options) >= 3:
            break
    return ClarificationModel(
        rule="route_decision",
        question=decision.question,
        why=decision.reason,
        options=options,
    )


def _legacy_model(h):
    return LegacyHintModel(
        problem_type_candidates=h.problem_type_candidates,
        applicable_equations=h.applicable_equations,
        not_applicable_equations=h.not_applicable_equations,
        cautions=h.cautions,
        detected_cues=h.detected_cues,
    )


def diagnose_problem(
    problem_text: str,
    student_solution: str | None = None,
    canonical: "CanonicalProblem | None" = None,
    physical_model=None,
    registry: SolverRegistry | None = None,
    route_decision=None,
) -> DiagnosisResponse:
    """canonical을 직접 주면 그 기준으로 진단한다 (clarify patch 이후 재진단용)."""
    if canonical is None:
        canonical = extract_problem(problem_text)
    hints = make_legacy_hints(canonical)
    registry = registry or SolverRegistry()
    route_decision = route_decision or registry.route(canonical)
    solver = registry.select(canonical, decision=route_decision)
    cards = build_diagnosis_cards(canonical, hints, solver)
    legacy_selected_solver = solver.name if solver is not None else None
    legacy_solver_reason = solver.reason if solver is not None else None
    physical_model = physical_model or build_physical_model(canonical)

    return DiagnosisResponse(
        ok=True,
        fbd_diagram_svg=build_fbd_svg(canonical),
        fbd_annotations=build_fbd_annotations(canonical),
        canonical=_canonical_model(canonical),
        legacy_hints=_legacy_model(hints),
        selected_solver=legacy_selected_solver,
        solver_reason=legacy_solver_reason,
        route_decision=_route_decision_model(route_decision),
        fbd=cards.fbd,
        coordinate_guide=cards.coordinate_guide,
        applicable_equations=cards.applicable_equations,
        not_applicable_equations=cards.not_applicable_equations,
        cautions=cards.cautions,
        next_questions=cards.next_questions,
        physical_model=_physical_model_payload(physical_model.to_dict(), route_decision),
    )


def solve_problem(problem_text: str, student_solution: str | None = None, clarify_patch: dict | None = None, canonical_patch: dict | None = None) -> SolveResponse:
    canonical = extract_problem(problem_text)
    if clarify_patch:
        # 되묻기 선택지 적용. 화이트리스트 밖 patch는 즉시 거절 (API 노출 지점).
        canonical = apply_clarify_patch(canonical, clarify_patch)
    if canonical_patch:
        canonical = apply_clarify_patch(canonical, canonical_patch)
    # Phase 35: diagnosis는 반드시 patch가 반영된 canonical 기준으로 만든다.
    # (이전에는 patch 전 원문으로 진단해 selected_solver/physical_model이
    #  사용자가 선택한 해석과 어긋난 채 화면에 남았다.)
    # Phase 45 vertical slices share one typed/legacy model across diagnosis,
    # solving, StepCards, and response serialization.
    physical_model = build_physical_model(canonical)
    registry = SolverRegistry()
    route_decision = registry.route(canonical)
    diagnosis = diagnose_problem(
        problem_text,
        student_solution,
        canonical=canonical,
        physical_model=physical_model,
        registry=registry,
        route_decision=route_decision,
    )
    solver = registry.select(canonical, decision=route_decision)

    if not solver:
        verification = VerificationReportSchema(
            passed=False,
            warnings=[
                "풀이 전에 물리 모형 또는 추가 입력 확인이 필요합니다."
                if route_decision.status == "clarify"
                else "현재 MVP solver가 직접 지원하지 않는 유형입니다."
            ],
            errors=[],
            checks=[],
        )
        clar = (
            build_clarification(canonical)
            if route_decision.status == "clarify"
            else None
        )
        clarification_model = None
        if clar is not None:
            clarification_model = ClarificationModel(
                rule=clar.rule,
                question=clar.question,
                why=clar.why,
                options=[
                    ClarificationOptionModel(
                        id=o.id, label=o.label, description=o.description,
                        patch=o.patch, needs_value=o.needs_value,
                    )
                    for o in clar.options
                ],
            )
        if clarification_model is None and route_decision.status == "clarify":
            clarification_model = _route_clarification_model(route_decision, canonical)
        response = SolveResponse(
            ok=False,
            diagnosis=diagnosis,
            answer=None,
            answers=[],
            steps=_partial_guidance_steps(canonical),
            verification=verification,
            unsupported_reason=(
                clar.question if clar is not None
                else (
                    route_decision.question
                    or route_decision.reason
                    or ("; ".join(canonical.missing_info) if canonical.missing_info else "아직 이 유형을 계산까지 지원하지 않습니다. 진단 카드만 참고하세요.")
                )
            ),
            clarification=clarification_model,
            route_decision=_route_decision_model(route_decision),
            physical_model=diagnosis.physical_model,
        )
        response.teacher_summary = build_teacher_summary(response)
        response.concept_summary = build_concept_summary(response)
        response.common_mistakes = build_common_mistakes(response)
        response.study_tips = build_study_tips(response)
        response.equation_sheet = build_equation_sheet(response)
        return response

    conflicts = list(canonical.canonical_v2.conflicts) if canonical.canonical_v2 is not None else []
    domain_errors = [
        issue.message
        for issue in check_knowns(canonical.knowns, system_type=canonical.system_type)
        if issue.kind == "error"
    ]
    if conflicts:
        result = SolverResult(
            ok=False,
            verification=VerificationReport(
                passed=False,
                errors=["contradictory explicit inputs: " + "; ".join(conflicts)],
            ),
            unsupported_reason="서로 다른 값으로 적힌 조건을 먼저 확인해 주세요.",
        )
    elif domain_errors:
        result = SolverResult(
            ok=False,
            verification=VerificationReport(passed=False, errors=domain_errors),
            unsupported_reason="입력값의 물리적 범위를 확인해 주세요.",
        )
    else:
        result = (
            solver.solve(canonical, physical_model)
            if getattr(solver, "uses_prebuilt_physical_model", False)
            else solver.solve(canonical)
        )
        # Phase 30: 물리 검증 스위트 (차원 · 타당성 · 역대입 잔차).
        # 검증 error는 '조용한 오답'이므로 ok=False로 강등한다.
        suite_report = verify_result(canonical, result)
        result.verification = merge_reports(result.verification, suite_report)
    # 강등은 아래 apply_result_gate 한 곳에서만 수행한다 (Phase 33 통합).
    model_cards = physical_model_step_cards(physical_model)
    all_steps = model_cards + result.steps
    response = SolveResponse(
        ok=result.ok,
        diagnosis=diagnosis,
        answer=AnswerModel(**result.answer.__dict__) if result.answer else None,
        answers=_answers_from_result(result),
        steps=[StepCardSchema(**s.__dict__) for s in all_steps],
        verification=VerificationReportSchema(**result.verification.__dict__),
        unsupported_reason=result.unsupported_reason,
        route_decision=_route_decision_model(route_decision),
        physical_model=_physical_model_payload(physical_model.to_dict(), route_decision),
    )
    # 실패 응답도 "완전히 못 풂" 대신 현재 가능한 것/필요한 조건을 보여준다.
    if not response.ok and not response.steps:
        response.steps = _partial_guidance_steps(canonical)

    # 되묻기: solver가 매치됐지만 값 부족 등으로 실패한 경우에도 질문을 제공.
    # (검증 강등 등 missing_info와 무관한 실패에는 규칙이 발동하지 않는다.)
    if not response.ok and response.clarification is None:
        clar = build_clarification(canonical)
        if clar is not None:
            response.clarification = ClarificationModel(
                rule=clar.rule,
                question=clar.question,
                why=clar.why,
                options=[
                    ClarificationOptionModel(id=o.id, label=o.label, description=o.description, patch=o.patch, needs_value=o.needs_value)
                    for o in clar.options
                ],
            )
            if response.unsupported_reason and response.unsupported_reason.startswith("필수 조건"):
                response.unsupported_reason = clar.question

    answer_report = validate_solve_response(response)
    if answer_report.errors:
        response.verification.errors.extend(["answer consistency: " + e for e in answer_report.errors])
    if answer_report.warnings:
        response.verification.warnings.extend(["answer consistency: " + w for w in answer_report.warnings])

    # 유일한 강등 지점: verification.errors 를 보고 ok/passed/unsupported_reason 을 결정.
    apply_result_gate(response)
    response.teacher_summary = build_teacher_summary(response)
    response.concept_summary = build_concept_summary(response)
    response.common_mistakes = build_common_mistakes(response)
    response.study_tips = build_study_tips(response)
    response.equation_sheet = build_equation_sheet(response)
    return response


def feedback_on_solution(problem_text: str, student_solution: str) -> FeedbackResponse:
    canonical = extract_problem(problem_text)
    fb = analyze_student_solution(canonical, student_solution)
    return FeedbackResponse(**fb)
