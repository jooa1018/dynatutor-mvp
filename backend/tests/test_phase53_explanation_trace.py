from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.schemas.solution import (
    AnswerItemModel,
    CandidateSolutionModel,
    CanonicalProblemModel,
    DiagnosisResponse,
    ExplanationTraceModel,
    LegacyHintModel,
    SelectionDecisionModel,
    SolveResponse,
    VerificationReport as VerificationReportModel,
)
from engine import services
from engine.explanation import project_explanation_from_trace
from engine.explanation_trace import build_explanation_trace_payload
from engine.models import (
    CalculationCoordinateFrame,
    CanonicalProblem,
    EquationEvidence,
    OutputEvidenceLink,
    Quantity,
    SemanticFactEvidence,
    SolverExplanationEvidence,
    SolverResult,
    SubstitutionEvidence,
)
from engine.verification.gate import apply_result_gate


def _canonical(*, assumptions=()) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="synthetic_force",
        knowns={
            "F": Quantity(symbol="F", value=10.0, unit="N", source_text="must not leak"),
            "m": Quantity(symbol="m", value=2.0, unit="kg", source_text="must not leak"),
        },
        assumptions=list(assumptions),
        raw_text="RAW_PHASE53_SENTINEL",
    )


def _diagnosis() -> DiagnosisResponse:
    return DiagnosisResponse(
        ok=True,
        canonical=CanonicalProblemModel(system_type="synthetic_force"),
        legacy_hints=LegacyHintModel(),
        selected_solver="synthetic_solver_internal",
        solver_reason="structured synthetic route",
    )


def _answer(output_key: str, symbol: str, numeric: float, unit: str) -> AnswerItemModel:
    return AnswerItemModel(
        label=output_key,
        symbol=symbol,
        numeric=numeric,
        unit=unit,
        display=f"{numeric:g} {unit}",
        role="primary",
        output_key=output_key,
    )


def _response(answers: list[AnswerItemModel]) -> SolveResponse:
    candidate = CandidateSolutionModel(
        candidate_id="candidate:selected:internal",
        numerical_mapping={answer.output_key: answer.numeric for answer in answers},
    )
    return SolveResponse(
        ok=True,
        diagnosis=_diagnosis(),
        answers=answers,
        verification=VerificationReportModel(passed=True, policy_version="phase53-test"),
        selection_decision=SelectionDecisionModel(
            status="selected",
            selected_candidate=candidate,
            selection_policy="synthetic exact-output policy",
            explanation="selected by the test fixture",
            policy_version="phase53-test",
        ),
    )


def _evidence(answers: list[AnswerItemModel], *, typed_assumption: bool = False) -> SolverExplanationEvidence:
    facts = (
        SemanticFactEvidence("known:F", "F", 10.0, "N"),
        SemanticFactEvidence("known:m", "m", 2.0, "kg"),
    )
    assumptions = ()
    assumption_ids: tuple[str, ...] = ()
    if typed_assumption:
        assumptions = (
            SemanticFactEvidence(
                "assumption:air_resistance",
                "air_resistance",
                "ignored",
                source="solver_assumption",
                classification="assumed",
            ),
        )
        assumption_ids = ("assumption:air_resistance",)

    equations = []
    substitutions = []
    outputs = []
    for index, answer in enumerate(answers):
        equation_id = f"eq:internal:{index}"
        substitution_id = f"sub:internal:{index}"
        output_id = f"derived:internal:{index}"
        equations.append(
            EquationEvidence(
                equation_id=equation_id,
                expression=f"{answer.symbol} = F / m",
                source="solver_equation",
                provenance="newton_second_law",
                fact_ids=("known:F", "known:m") + assumption_ids,
                output_ids=(output_id,),
            )
        )
        substitutions.append(
            SubstitutionEvidence(
                substitution_id=substitution_id,
                equation_id=equation_id,
                expression=f"{answer.symbol} = 10 / 2 = {answer.numeric:g} {answer.unit}",
                output_id=output_id,
                fact_ids=("known:F", "known:m") + assumption_ids,
            )
        )
        outputs.append(
            OutputEvidenceLink(
                output_id=output_id,
                output_key=answer.output_key,
                candidate_id="candidate:selected:internal",
                numeric=answer.numeric,
                unit=answer.unit,
                symbol=answer.symbol,
                role=answer.role,
                response_index=index,
                equation_ids=(equation_id,),
                substitution_ids=(substitution_id,),
            )
        )
    return SolverExplanationEvidence(
        coordinate_frame=CalculationCoordinateFrame(
            frame_id="frame:internal",
            coordinate_system="cartesian_1d",
            axes=("x",),
            positive_directions=("along_applied_force",),
            units=("m",),
            source="solver_calculation",
            status="resolved",
        ),
        explicit_facts=facts,
        assumptions=assumptions,
        equations=tuple(equations),
        substitutions=tuple(substitutions),
        outputs=tuple(outputs),
    )


def _build(response, canonical, evidence, *, physical_model=None):
    payload = build_explanation_trace_payload(
        response=response,
        canonical=canonical,
        physical_model=physical_model or {},
        result=SolverResult(ok=True, explanation_evidence=evidence),
        selected_solver="synthetic_solver_internal",
        route_reason="structured synthetic route",
        route_decision=SimpleNamespace(status="select", warnings=[]),
    )
    return ExplanationTraceModel(**payload)


_STALE_PUBLIC_SENTINEL = "STALE_INTERNAL_530153"


def _seed_stale_public_physics(response: SolveResponse) -> None:
    diagnosis = response.diagnosis
    diagnosis.fbd_diagram_svg = f"<svg>{_STALE_PUBLIC_SENTINEL}</svg>"
    diagnosis.fbd_annotations = [f"rejected value 987653 {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.fbd = [f"F = 530153 N {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.coordinate_guide = [f"positive x invented {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.applicable_equations = [f"x = 530153 {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.not_applicable_equations = [f"y = 987653 {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.cautions = [f"physics caution {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.next_questions = [f"untraced question {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.physical_model = {"equation": f"z = 530153 {_STALE_PUBLIC_SENTINEL}"}
    diagnosis.legacy_hints.problem_type_candidates = [_STALE_PUBLIC_SENTINEL]
    diagnosis.legacy_hints.applicable_equations = [f"q = 530153 {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.legacy_hints.not_applicable_equations = [f"r = 987653 {_STALE_PUBLIC_SENTINEL}"]
    diagnosis.legacy_hints.cautions = [_STALE_PUBLIC_SENTINEL]
    diagnosis.legacy_hints.detected_cues = [_STALE_PUBLIC_SENTINEL]
    response.physical_model = {"internal_id": _STALE_PUBLIC_SENTINEL, "value": 987653}


def _assert_scrubbed_public_physics(response: SolveResponse, *, fully_grounded: bool) -> None:
    diagnosis = response.diagnosis
    assert diagnosis.fbd_diagram_svg is None
    assert diagnosis.fbd_annotations == []
    assert diagnosis.fbd == []
    assert diagnosis.not_applicable_equations == []
    assert diagnosis.cautions == []
    assert diagnosis.next_questions == []
    assert diagnosis.physical_model is None
    assert diagnosis.legacy_hints.problem_type_candidates == []
    assert diagnosis.legacy_hints.applicable_equations == []
    assert diagnosis.legacy_hints.not_applicable_equations == []
    assert diagnosis.legacy_hints.cautions == []
    assert diagnosis.legacy_hints.detected_cues == []
    assert response.physical_model is None
    if fully_grounded:
        assert diagnosis.coordinate_guide == [
            "cartesian_1d",
            "x: along_applied_force",
        ]
        assert diagnosis.applicable_equations == [
            equation.expression for equation in response.explanation_trace.equations
        ]
    else:
        assert diagnosis.coordinate_guide == []
        assert diagnosis.applicable_equations == []
    assert _STALE_PUBLIC_SENTINEL not in json.dumps(
        response.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "answers",
    [
        [_answer("acceleration", "a", 5.0, "m/s^2")],
        [
            _answer("acceleration", "a", 5.0, "m/s^2"),
            _answer("force_ratio", "r", 5.0, "1"),
        ],
    ],
    ids=("single-answer", "multi-answer"),
)
def test_fully_grounded_trace_requires_exact_selected_output_links(answers):
    canonical = _canonical()
    response = _response(answers)
    trace = _build(response, canonical, _evidence(answers))

    assert trace.status == "fully_grounded"
    assert [item.output_key for item in trace.answer_derivation] == [
        answer.output_key for answer in answers
    ]
    assert [item.numeric for item in trace.answer_derivation] == [
        answer.numeric for answer in answers
    ]
    assert trace.candidate_summary.selected_candidate_id == "candidate:selected:internal"

    response.explanation_trace = trace
    project_explanation_from_trace(response)
    student_text = json.dumps(
        {
            "steps": [step.model_dump() for step in response.steps],
            "teacher_summary": response.teacher_summary,
            "concept_summary": response.concept_summary,
            "common_mistakes": response.common_mistakes,
            "equation_sheet": response.equation_sheet,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for internal_id in (
        "candidate:selected:internal",
        "frame:internal",
        "eq:internal:",
        "sub:internal:",
        "derived:internal:",
    ):
        assert internal_id not in student_text
    assert "RAW_PHASE53_SENTINEL" not in trace.model_dump_json()
    assert "must not leak" not in trace.model_dump_json()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("problem_text", "expected_status"),
    [
        ("30도 경사면 위 블록의 가속도는?", "ambiguous"),
        ("오늘 저녁 메뉴를 추천해 줘.", "unsupported"),
    ],
)
def test_service_serialization_scrubs_actual_clarify_and_unsupported_responses(
    problem_text, expected_status
):
    response = services.solve_problem(problem_text)

    assert response.explanation_trace.status == expected_status
    _assert_scrubbed_public_physics(response, fully_grounded=False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("problem_text", "expected_solver", "expected_equation"),
    [
        (
            "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
            "incline_no_friction",
            "mg sinθ",
        ),
        (
            "정지 상태에서 원판이 미끄러지지 않고 경사면을 높이 1.5 m만큼 굴러 내려간다. 속도를 구하라.",
            "pure_rolling_energy",
            "v_G = ωR",
        ),
    ],
    ids=("incline", "rolling"),
)
def test_real_successful_unmigrated_solver_keeps_legacy_product_projection(
    problem_text, expected_solver, expected_equation
):
    response = services.solve_problem(problem_text)

    assert response.ok is True
    assert response.diagnosis.selected_solver == expected_solver
    assert response.answer is not None
    assert response.explanation_trace is None
    assert response.steps
    assert response.equation_sheet
    assert response.physical_model is not None
    assert response.diagnosis.physical_model is not None
    assert response.diagnosis.fbd_diagram_svg is not None
    assert response.diagnosis.fbd_annotations
    combined_equations = (
        response.diagnosis.applicable_equations
        + response.diagnosis.not_applicable_equations
        + response.equation_sheet
    )
    assert any(expected_equation in equation for equation in combined_equations)


@pytest.mark.unit
def test_direct_finalizer_preserves_all_legacy_fields_only_for_success_without_evidence():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    original_answers = [answer.model_dump() for answer in response.answers]
    _seed_stale_public_physics(response)
    response.diagnosis.not_applicable_equations = ["legacy equation sentinel"]
    legacy_step = SimpleNamespace(
        title="legacy model card",
        body="legacy solver derivation",
        math="a = F / m",
    )

    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={"legacy": True},
        result=SolverResult(ok=True),
        selected_solver="unmigrated_legacy_solver",
        route_decision=SimpleNamespace(status="select", reason="legacy", warnings=[]),
        legacy_steps=(legacy_step,),
    )

    assert response.explanation_trace is None
    assert response.ok is True
    assert [answer.model_dump() for answer in response.answers] == original_answers
    assert [step.title for step in response.steps] == ["legacy model card"]
    assert response.diagnosis.fbd_diagram_svg == f"<svg>{_STALE_PUBLIC_SENTINEL}</svg>"
    assert response.diagnosis.fbd_annotations == [
        f"rejected value 987653 {_STALE_PUBLIC_SENTINEL}"
    ]
    assert response.diagnosis.physical_model == {
        "equation": f"z = 530153 {_STALE_PUBLIC_SENTINEL}"
    }
    assert response.physical_model == {
        "internal_id": _STALE_PUBLIC_SENTINEL,
        "value": 987653,
    }
    assert "legacy equation sentinel" in response.equation_sheet


@pytest.mark.unit
def test_failed_unmigrated_result_never_enters_legacy_compatibility_path():
    response = _response([_answer("acceleration", "a", 5.0, "m/s^2")])
    _seed_stale_public_physics(response)
    response.ok = False
    response.answers = []
    response.verification.passed = False
    response.verification.errors.append("result gate rejected final answer")

    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={"legacy": True},
        result=SolverResult(ok=False),
        selected_solver="unmigrated_legacy_solver",
        route_decision=SimpleNamespace(status="select", reason="legacy", warnings=[]),
        legacy_steps=(
            SimpleNamespace(title="stale", body=_STALE_PUBLIC_SENTINEL, math=None),
        ),
    )

    assert response.explanation_trace is not None
    assert response.explanation_trace.status == "withheld"
    _assert_scrubbed_public_physics(response, fully_grounded=False)


@pytest.mark.unit
def test_service_finalizer_rebuilds_fully_grounded_public_fields_only_from_trace():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    _seed_stale_public_physics(response)

    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={"untraced": _STALE_PUBLIC_SENTINEL},
        result=SolverResult(ok=True, explanation_evidence=_evidence(answers)),
        selected_solver="synthetic_solver_internal",
        route_decision=SimpleNamespace(
            status="select", reason="structured synthetic route", warnings=[]
        ),
    )

    assert response.explanation_trace.status == "fully_grounded"
    _assert_scrubbed_public_physics(response, fully_grounded=True)


@pytest.mark.unit
def test_structured_malformed_evidence_stays_strict_and_scrubs_stale_projection():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    _seed_stale_public_physics(response)
    original_answers = [answer.model_dump() for answer in response.answers]
    malformed = replace(_evidence(answers), equations=())

    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={"untraced": _STALE_PUBLIC_SENTINEL},
        result=SolverResult(ok=True, explanation_evidence=malformed),
        selected_solver="synthetic_solver_internal",
        route_decision=SimpleNamespace(
            status="select", reason="structured synthetic route", warnings=[]
        ),
        legacy_steps=(
            SimpleNamespace(title="stale", body=_STALE_PUBLIC_SENTINEL, math=None),
        ),
    )

    assert response.ok is True
    assert [answer.model_dump() for answer in response.answers] == original_answers
    assert response.explanation_trace is not None
    assert response.explanation_trace.status != "fully_grounded"
    assert response.explanation_trace.answer_derivation == []
    _assert_scrubbed_public_physics(response, fully_grounded=False)


@pytest.mark.unit
def test_actual_gate_demotion_then_service_finalization_has_no_stale_projection():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    _seed_stale_public_physics(response)
    response.verification.errors.append("contradictory explicit inputs")

    apply_result_gate(response)
    assert response.ok is False
    assert response.answer is None
    assert response.answers == []
    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={"untraced": _STALE_PUBLIC_SENTINEL},
        result=SolverResult(ok=True, explanation_evidence=_evidence(answers)),
        selected_solver="synthetic_solver_internal",
        route_decision=SimpleNamespace(
            status="select", reason="structured synthetic route", warnings=[]
        ),
    )

    assert response.explanation_trace.status == "contradictory"
    assert response.explanation_trace.answer_derivation == []
    _assert_scrubbed_public_physics(response, fully_grounded=False)


@pytest.mark.unit
def test_explicit_facts_and_assumptions_are_separate_and_linked():
    canonical = _canonical()
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    trace = _build(_response(answers), canonical, _evidence(answers, typed_assumption=True))

    assert trace.status == "fully_grounded"
    assert {fact.classification for fact in trace.explicit_facts} == {"explicit"}
    assert [fact.value for fact in trace.assumptions] == ["ignored"]
    assert all(fact.classification == "assumed" for fact in trace.assumptions)
    assert any(step.kind == "assumptions" for step in trace.student_steps)


@pytest.mark.unit
def test_post_gate_cleared_answer_never_receives_a_derivation():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    response.ok = False
    response.answers = []
    response.answer = None
    response.verification.passed = False
    response.verification.errors.append("gate rejected final answer")

    trace = _build(response, _canonical(), _evidence(answers))

    assert trace.status == "withheld"
    assert trace.answer_derivation == []
    assert all(step.kind not in {"equation", "substitution", "answer"} for step in trace.student_steps)
    assert "5 m/s^2" not in json.dumps([step.model_dump() for step in trace.student_steps])


@pytest.mark.unit
def test_default_coordinate_is_omitted_and_resolved_mismatch_is_withheld():
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    evidence = _evidence(answers)

    default_frame = replace(evidence.coordinate_frame, source="physical_model_default", status="default")
    default_trace = _build(
        response,
        _canonical(),
        replace(evidence, coordinate_frame=default_frame),
    )
    assert default_trace.coordinate_frame is None
    assert default_trace.status == "partial"
    assert any("coordinates are unavailable" in warning for warning in default_trace.warnings)

    mismatch_trace = _build(
        response,
        _canonical(),
        evidence,
        physical_model={
            "coordinate_frame": {
                "coordinate_system": "cartesian_1d",
                "axes": ["x"],
                "positive_directions": ["opposite_applied_force"],
                "units": ["m"],
                "source": "canonical_explicit",
                "status": "resolved",
            }
        },
    )
    assert mismatch_trace.status == "withheld"
    assert mismatch_trace.answer_derivation == []
    assert any("coordinate frames disagree" in warning for warning in mismatch_trace.warnings)


@pytest.mark.unit
def test_repeated_bytes_and_llm_environment_toggle_are_invariant(monkeypatch):
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    canonical = _canonical()
    response = _response(answers)
    evidence = _evidence(answers)

    monkeypatch.setenv("OPENAI_API_KEY", "phase53-disabled-a")
    first = _build(response, canonical, evidence).model_dump_json()
    monkeypatch.setenv("OPENAI_API_KEY", "phase53-disabled-b")
    monkeypatch.setenv("ENABLE_LLM_EXPLANATION", "1")
    second = _build(response, canonical, evidence).model_dump_json()
    third = _build(response, canonical, evidence).model_dump_json()

    assert first == second == third


@pytest.mark.unit
def test_builder_failure_preserves_product_answer(monkeypatch):
    answers = [_answer("acceleration", "a", 5.0, "m/s^2")]
    response = _response(answers)
    _seed_stale_public_physics(response)
    original_dump = [answer.model_dump() for answer in response.answers]

    def fail_builder(**_kwargs):
        raise RuntimeError("sensitive builder detail")

    monkeypatch.setattr(services, "build_explanation_trace_payload", fail_builder)
    services._finalize_public_explanation(
        response,
        canonical=_canonical(),
        physical_model={},
        result=SolverResult(ok=True, explanation_evidence=_evidence(answers)),
        selected_solver="synthetic_solver_internal",
        route_decision=SimpleNamespace(status="select", reason="synthetic", warnings=[]),
    )

    assert [answer.model_dump() for answer in response.answers] == original_dump
    assert response.ok is True
    assert response.explanation_trace.status == "withheld"
    assert response.explanation_trace.answer_derivation == []
    assert "sensitive builder detail" not in response.explanation_trace.model_dump_json()
    _assert_scrubbed_public_physics(response, fully_grounded=False)
