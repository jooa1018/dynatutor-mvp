from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.schemas.solution import (
    AnswerModel,
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
    Answer,
    AnswerItem,
    CalculationCoordinateFrame,
    CanonicalProblem,
    EquationEvidence,
    OutputEvidenceLink,
    Quantity,
    SemanticFactEvidence,
    SolverExplanationEvidence,
    SolverResult,
    SubstitutionEvidence,
    VerificationReport,
)
from engine.observability.trace import SolveTraceCollector
from engine.physics_core.validators import (
    CandidateSolution,
    CandidateSolveBatch,
    SelectionDecision,
)
from engine.solvers.registry import SolverRegistry
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
    candidate_mapping = {}
    for answer in answers:
        candidate_mapping[answer.symbol] = answer.numeric
        candidate_mapping.setdefault(answer.output_key, answer.numeric)
    candidate = CandidateSolutionModel(
        candidate_id="candidate:selected:internal",
        numerical_mapping=candidate_mapping,
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
                # ``str(float)`` preserves Python's shortest round-trippable
                # representation.  ``:g`` defaults to six significant digits
                # and would fabricate a different last calculation value for
                # legitimate six-decimal delivery fixtures.
                expression=f"{answer.symbol} = 10 / 2 = {answer.numeric} {answer.unit}",
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
                candidate_key=answer.symbol,
                candidate_numeric=answer.numeric,
                delivery_candidate_id="candidate:selected:internal",
                delivery_candidate_key=answer.symbol,
                delivery_transform="identity",
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


def _build(
    response,
    canonical,
    evidence,
    *,
    physical_model=None,
    selected_solver="synthetic_solver_internal",
):
    payload = build_explanation_trace_payload(
        response=response,
        canonical=canonical,
        physical_model=physical_model or {},
        result=SolverResult(ok=True, explanation_evidence=evidence),
        selected_solver=selected_solver,
        route_reason="structured synthetic route",
        route_decision=SimpleNamespace(status="select", warnings=[]),
        delivery_decision=response.selection_decision,
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
            _answer("normal_force", "N", 5.0, "N"),
        ],
    ],
    ids=("single-answer", "multi-answer"),
)
def test_fully_grounded_trace_requires_exact_selected_output_links(answers):
    canonical = _canonical()
    response = _response(answers)
    trace = _build(response, canonical, _evidence(answers))

    assert trace.schema == "dynatutor.explanation_trace"
    assert trace.version == "1.0"
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
    ("case", "expected_grounded"),
    [
        ("none-key-unique-primary", True),
        ("coherent-explicit-key", True),
        ("five-vs-six-decimals", False),
        ("signed-zero", False),
        ("unit-mismatch", False),
        ("wrong-explicit-key", False),
        ("missing-primary-key", False),
    ],
)
def test_top_level_answer_closes_exact_first_primary_compatibility_edge(
    case, expected_grounded
):
    delivered_numeric = -0.0 if case == "signed-zero" else 5.123457
    answers = [_answer("acceleration", "a", delivered_numeric, "m/s^2")]
    response = _response(answers)
    evidence = _evidence(answers)
    top_numeric = delivered_numeric
    top_unit = "m/s^2"
    top_key = None
    if case == "coherent-explicit-key":
        top_key = "acceleration"
    elif case == "five-vs-six-decimals":
        top_numeric = 5.12346
    elif case == "signed-zero":
        top_numeric = 0.0
    elif case == "unit-mismatch":
        top_unit = "N"
    elif case == "wrong-explicit-key":
        top_key = "normal_force"
    elif case == "missing-primary-key":
        response.answers[0].output_key = None
    response.answer = AnswerModel(
        symbolic="compatibility authority",
        numeric=top_numeric,
        unit=top_unit,
        display="unchanged top-level display",
        output_key=top_key,
    )
    original_answer = response.answer.model_dump()
    original_answers = [item.model_dump() for item in response.answers]

    trace = _build(response, _canonical(), evidence)

    assert (trace.status == "fully_grounded") is expected_grounded
    assert bool(trace.answer_derivation) is expected_grounded
    assert response.answer.model_dump() == original_answer
    assert [item.model_dump() for item in response.answers] == original_answers


@pytest.mark.unit
def test_top_level_none_key_rejects_ambiguous_duplicate_primary_semantics():
    answers = [
        _answer("friction_force", "f_s", 3.0, "N"),
        _answer("friction_force", "f_s,max", 5.0, "N"),
    ]
    response = _response(answers)
    response.answer = AnswerModel(
        symbolic="legacy friction answer",
        numeric=3.0,
        unit="N",
        display="legacy unchanged",
        output_key=None,
    )
    trace = _build(response, _canonical(), _evidence(answers))

    assert trace.status == "withheld"
    assert trace.answer_derivation == []
    assert any("unique semantic key" in warning for warning in trace.warnings)


@pytest.mark.unit
def test_delivery_validation_uses_one_fresh_candidate_and_preserves_raw_selection(
    monkeypatch,
):
    raw_value = 5.123456789
    raw_candidate = CandidateSolution(
        candidate_id="raw:kinematics:selected",
        symbolic_mapping={"a": raw_value},
        numerical_mapping={"a": raw_value},
    )
    raw_decision = SelectionDecision(
        status="selected",
        selected_candidate=raw_candidate,
        selection_policy="raw-physics-selection",
    )
    result = SolverResult(
        ok=True,
        answers=[
            AnswerItem(
                label="가속도",
                symbol="a",
                numeric=round(raw_value, 6),
                unit="m/s^2",
                display="a = 5.123 m/s^2",
                output_key="acceleration",
            )
        ],
        selection_decision=raw_decision,
    )
    original_validate = services.validate_output_candidates
    observed_candidates = []

    def count_validation(candidates, context):
        candidates = list(candidates)
        observed_candidates.extend(candidates)
        return original_validate(candidates, context)

    monkeypatch.setattr(services, "validate_output_candidates", count_validation)
    delivery = services._validate_delivered_result(
        result,
        solver_name="constant_acceleration_1d",
        requested_outputs=["acceleration"],
    )

    assert len(observed_candidates) == 1
    assert observed_candidates[0] is not raw_candidate
    assert observed_candidates[0].candidate_id == (
        "delivery:constant_acceleration_1d:solve-response"
    )
    assert result.selection_decision is raw_decision
    assert raw_candidate.symbolic_mapping == {"a": raw_value}
    assert raw_candidate.numerical_mapping == {"a": raw_value}
    assert raw_candidate.validation_checks == []
    assert raw_candidate.rejection_reasons == []
    assert delivery.status == "selected"
    assert delivery.selected_candidate is observed_candidates[0]
    raw_authority = services._reconcile_selection_authorities(
        result, raw_decision, delivery
    )
    assert raw_authority is raw_decision
    assert result.selection_decision is raw_decision

    rejected_delivery = SelectionDecision(
        status="no_valid_solution",
        selection_policy="delivery-output-rejected",
    )
    raw_authority = services._reconcile_selection_authorities(
        result, raw_decision, rejected_delivery
    )
    assert raw_authority is raw_decision
    assert result.selection_decision is rejected_delivery

    direct = SolverResult(ok=True)
    direct_authority = services._reconcile_selection_authorities(
        direct, None, delivery
    )
    assert direct_authority is delivery
    assert direct.selection_decision is delivery


@pytest.mark.unit
@pytest.mark.parametrize(
    (
        "case",
        "direct",
        "raw_status",
        "delivery_output_key",
        "expected_public_status",
        "expected_verify_calls",
        "expected_ok",
    ),
    [
        ("raw-and-delivery-selected", False, "selected", "acceleration", "selected", 1, True),
        (
            "raw-selected-delivery-rejected",
            False,
            "selected",
            "normal_force",
            "no_valid_solution",
            0,
            False,
        ),
        ("raw-ambiguous-delivery-selected", False, "ambiguous", "acceleration", "ambiguous", 0, False),
        (
            "raw-rejected-delivery-selected",
            False,
            "no_valid_solution",
            "acceleration",
            "no_valid_solution",
            0,
            False,
        ),
        ("direct-identity", True, None, "acceleration", "selected", 1, True),
    ],
)
def test_full_service_path_preserves_raw_and_delivery_authority_graph(
    monkeypatch,
    case,
    direct,
    raw_status,
    delivery_output_key,
    expected_public_status,
    expected_verify_calls,
    expected_ok,
):
    raw_candidate = CandidateSolution(
        candidate_id=f"raw:{case}",
        symbolic_mapping={"a": 5.0},
        numerical_mapping={"a": 5.0},
    )
    raw_decision = None
    if raw_status == "selected":
        raw_decision = SelectionDecision(
            status="selected",
            selected_candidate=raw_candidate,
            selection_policy="injected-raw-selection",
        )
    elif raw_status == "ambiguous":
        raw_decision = SelectionDecision(
            status="ambiguous",
            valid_alternatives=[raw_candidate],
            selection_policy="injected-raw-selection",
        )
    elif raw_status == "no_valid_solution":
        raw_decision = SelectionDecision(
            status="no_valid_solution",
            selection_policy="injected-raw-selection",
        )

    symbol = "a" if delivery_output_key == "acceleration" else "N"
    unit = "m/s^2" if delivery_output_key == "acceleration" else "N"
    result = SolverResult(
        ok=True,
        answer=Answer(
            symbolic="injected exact answer",
            numeric=5.0,
            unit=unit,
            display=f"{symbol} = 5 {unit}",
            output_key=delivery_output_key,
        ),
        answers=[
            AnswerItem(
                label="injected output",
                symbol=symbol,
                numeric=5.0,
                unit=unit,
                display=f"{symbol} = 5 {unit}",
                role="primary",
                output_key=delivery_output_key,
            )
        ],
        verification=VerificationReport(passed=True),
        selection_decision=raw_decision,
    )
    batch = CandidateSolveBatch(result=result, candidates=[raw_candidate])

    class RawSolver:
        name = "phase53_injected_raw"
        reason = "authority graph test"

        def solve_candidates(self, _canonical_problem):
            return batch

    class DirectSolver:
        name = "phase53_injected_direct"
        reason = "identity authority graph test"

        def solve(self, _canonical_problem):
            return result

    solver = DirectSolver() if direct else RawSolver()
    raw_candidate_before = raw_candidate.to_dict()
    raw_decision_before = raw_decision.to_dict() if raw_decision else None
    counts = {"validate": 0, "verify": 0, "gate": 0, "finalizer": 0}
    events = []
    delivery_candidates = []
    original_validate = services.validate_output_candidates
    original_gate = services.apply_result_gate
    original_finalizer = services._finalize_public_explanation

    def validate_once(candidates, context):
        counts["validate"] += 1
        candidates = list(candidates)
        delivery_candidates.extend(candidates)
        return original_validate(candidates, context)

    def verify_once(*_args, **_kwargs):
        counts["verify"] += 1
        return VerificationReport(passed=True, checks=["injected exact verification"])

    def gate_once(response):
        counts["gate"] += 1
        events.append("gate")
        return original_gate(response)

    def finalize_after_gate(*args, **kwargs):
        counts["finalizer"] += 1
        events.append("finalizer")
        assert events[-2:] == ["gate", "finalizer"]
        return original_finalizer(*args, **kwargs)

    monkeypatch.setattr(
        SolverRegistry,
        "select",
        lambda self, canonical, decision=None: solver,
    )
    monkeypatch.setattr(services, "validate_output_candidates", validate_once)
    monkeypatch.setattr(services, "verify_result", verify_once)
    monkeypatch.setattr(services, "apply_result_gate", gate_once)
    monkeypatch.setattr(
        services, "_finalize_public_explanation", finalize_after_gate
    )
    collector = SolveTraceCollector(f"phase53-authority-{case}")

    response = services.solve_problem(
        "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        trace_collector=collector,
    )

    assert counts == {
        "validate": 1,
        "verify": expected_verify_calls,
        "gate": 1,
        "finalizer": 1,
    }
    assert events == ["gate", "finalizer"]
    assert len(delivery_candidates) == 1
    assert delivery_candidates[0] is not raw_candidate
    assert response.selection_decision.status == expected_public_status
    assert response.ok is expected_ok
    assert raw_candidate.to_dict() == raw_candidate_before
    assert batch.candidates == [raw_candidate]
    assert raw_candidate.validation_checks == []
    assert raw_candidate.rejection_reasons == []
    if raw_decision is not None:
        assert raw_decision.to_dict() == raw_decision_before
    if expected_ok:
        assert response.answer.numeric == 5.0
        assert response.answers[0].numeric == 5.0
    core = collector.snapshot.to_dict()
    assert core["final_answer"]["ok"] is response.ok
    assert len(core["final_answer"]["answers"]) == len(response.answers)
    if expected_ok:
        assert core["final_answer"]["answers"][0]["numeric"] == (
            response.answers[0].numeric
        )


def _raw_delivery_trace(*, selected_solver, specs):
    answers = [
        _answer(spec["output_key"], spec["symbol"], spec["delivered"], spec["unit"])
        for spec in specs
    ]
    response = _response(answers)
    raw_id = "raw:selected:physics"
    raw_mapping = {spec["raw_key"]: spec["raw"] for spec in specs}
    response.selection_decision.selected_candidate = CandidateSolutionModel(
        candidate_id=raw_id,
        numerical_mapping=raw_mapping,
    )
    evidence = _evidence(answers)
    links = tuple(
        replace(
            link,
            candidate_id=raw_id,
            candidate_key=spec["raw_key"],
            candidate_numeric=spec["raw"],
            delivery_candidate_id="delivery:selected:response",
            delivery_candidate_key=spec["symbol"],
            delivery_transform=spec["transform"],
            decimal_places=spec["decimal_places"],
            delivery_policy_id=spec["policy_id"],
        )
        for link, spec in zip(evidence.outputs, specs, strict=True)
    )
    evidence = replace(evidence, outputs=links)
    delivery_mapping = {}
    for answer in answers:
        delivery_mapping[answer.symbol] = answer.numeric
        delivery_mapping.setdefault(answer.output_key, answer.numeric)
    delivery_decision = SimpleNamespace(
        status="selected",
        selected_candidate=SimpleNamespace(
            candidate_id="delivery:selected:response",
            numerical_mapping=delivery_mapping,
        ),
    )
    payload = build_explanation_trace_payload(
        response=response,
        canonical=_canonical(),
        physical_model={},
        result=SolverResult(ok=True, explanation_evidence=evidence),
        selected_solver=selected_solver,
        route_reason="structured rounded delivery",
        route_decision=SimpleNamespace(status="select", warnings=[]),
        delivery_decision=delivery_decision,
        raw_selection_decision=response.selection_decision,
    )
    return ExplanationTraceModel(**payload), response, evidence, delivery_decision


@pytest.mark.unit
@pytest.mark.parametrize(
    ("selected_solver", "specs"),
    [
        (
            "incline_no_friction",
            [
                {
                    "raw_key": "a",
                    "output_key": "acceleration",
                    "symbol": "a",
                    "raw": 5.123456789,
                    "delivered": round(5.123456789, 5),
                    "unit": "m/s^2",
                    "transform": "python_builtin_round",
                    "decimal_places": 5,
                    "policy_id": "incline.no_friction.acceleration.round5",
                }
            ],
        ),
        (
            "constant_acceleration_1d",
            [
                {
                    "raw_key": "a",
                    "output_key": "acceleration",
                    "symbol": "a",
                    "raw": 5.123456789,
                    "delivered": round(5.123456789, 6),
                    "unit": "m/s^2",
                    "transform": "python_builtin_round",
                    "decimal_places": 6,
                    "policy_id": "kinematics.acceleration.round6",
                },
                {
                    "raw_key": "t",
                    "output_key": "time",
                    "symbol": "t",
                    "raw": 2.987654321,
                    "delivered": round(2.987654321, 6),
                    "unit": "s",
                    "transform": "python_builtin_round",
                    "decimal_places": 6,
                    "policy_id": "kinematics.time.round6",
                },
            ],
        ),
        (
            "projectile_motion",
            [
                {
                    "raw_key": "t",
                    "output_key": "time",
                    "symbol": "t",
                    "raw": 1.23456789,
                    "delivered": round(1.23456789, 6),
                    "unit": "s",
                    "transform": "python_builtin_round",
                    "decimal_places": 6,
                    "policy_id": "projectile.general.time.round6",
                }
            ],
        ),
    ],
    ids=("five-digit", "six-digit-mixed-output", "projectile-general-six-digit"),
)
def test_raw_selected_delivery_selected_transform_triad_is_exact(
    selected_solver, specs
):
    trace, response, _evidence_value, delivery = _raw_delivery_trace(
        selected_solver=selected_solver,
        specs=specs,
    )

    assert response.selection_decision.status == "selected"
    assert delivery.status == "selected"
    assert trace.status == "fully_grounded"
    assert trace.candidate_summary.selected_candidate_id == "raw:selected:physics"
    assert [item.numeric for item in trace.answer_derivation] == [
        spec["delivered"] for spec in specs
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("selected_solver", "output_key", "symbol", "unit"),
    [
        ("projectile_motion", "time", "t", "s"),
        ("incline_with_friction", "acceleration", "a", "m/s^2"),
        ("pure_rolling_energy", "final_velocity", "v", "m/s"),
        ("collision_1d", "v1_after", "v1'", "m/s"),
        ("vertical_circle", "minimum_speed", "v_min", "m/s"),
        ("work_energy_speed", "final_velocity", "v", "m/s"),
        ("horizontal_friction_force", "friction_force", "f_k", "N"),
    ],
)
def test_direct_solver_paths_use_one_identity_authority_without_policy(
    selected_solver, output_key, symbol, unit
):
    answers = [_answer(output_key, symbol, 3.25, unit)]
    response = _response(answers)
    evidence = _evidence(answers)

    trace = _build(
        response,
        _canonical(),
        evidence,
        selected_solver=selected_solver,
    )

    assert trace.status == "fully_grounded"
    link = evidence.outputs[0]
    assert link.candidate_id == link.delivery_candidate_id
    assert link.delivery_transform == "identity"
    assert link.decimal_places is None
    assert link.delivery_policy_id == ""


def _rebuild_raw_delivery(response, evidence, delivery_decision, selected_solver):
    return ExplanationTraceModel(
        **build_explanation_trace_payload(
            response=response,
            canonical=_canonical(),
            physical_model={},
            result=SolverResult(ok=True, explanation_evidence=evidence),
            selected_solver=selected_solver,
            route_reason="structured rounded delivery",
            route_decision=SimpleNamespace(status="select", warnings=[]),
            delivery_decision=delivery_decision,
            raw_selection_decision=response.selection_decision,
        )
    )


@pytest.mark.unit
def test_signed_zero_is_preserved_across_python_round_delivery():
    spec = {
        "raw_key": "a",
        "output_key": "acceleration",
        "symbol": "a",
        "raw": -0.0,
        "delivered": round(-0.0, 5),
        "unit": "m/s^2",
        "transform": "python_builtin_round",
        "decimal_places": 5,
        "policy_id": "incline.no_friction.acceleration.round5",
    }
    trace, response, evidence, delivery = _raw_delivery_trace(
        selected_solver="incline_no_friction", specs=[spec]
    )
    assert trace.status == "fully_grounded"
    assert str(trace.answer_derivation[0].numeric).startswith("-0")

    response.answers[0].numeric = 0.0
    delivery.selected_candidate.numerical_mapping["a"] = 0.0
    delivery.selected_candidate.numerical_mapping["acceleration"] = 0.0
    evidence = replace(
        evidence,
        outputs=(replace(evidence.outputs[0], numeric=0.0),),
    )
    wrong_sign = _rebuild_raw_delivery(
        response, evidence, delivery, "incline_no_friction"
    )
    assert wrong_sign.status == "withheld"
    assert wrong_sign.answer_derivation == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    [
        "bool_raw",
        "nonfinite_raw",
        "bool_evidence",
        "nonfinite_evidence",
        "bool_delivery",
        "nonfinite_delivery",
        "bool_ndigits",
        "wrong_ndigits",
        "wrong_transform",
        "wrong_policy",
        "wrong_raw_id",
        "wrong_raw_key_same_numeric",
        "wrong_raw_value",
        "wrong_delivery_id",
        "wrong_delivery_key",
        "wrong_delivery_value",
        "same_id_does_not_imply_identity",
        "raw_ambiguous",
        "raw_rejected",
        "delivery_rejected",
        "missing_delivery_decision",
    ],
)
def test_raw_delivery_authority_rejects_adversarial_mismatch(case):
    raw = 5.123456789
    spec = {
        "raw_key": "a",
        "output_key": "acceleration",
        "symbol": "a",
        "raw": raw,
        "delivered": round(raw, 6),
        "unit": "m/s^2",
        "transform": "python_builtin_round",
        "decimal_places": 6,
        "policy_id": "kinematics.acceleration.round6",
    }
    _trace, response, evidence, delivery = _raw_delivery_trace(
        selected_solver="constant_acceleration_1d", specs=[spec]
    )
    link = evidence.outputs[0]

    if case == "bool_raw":
        response.selection_decision.selected_candidate.numerical_mapping["a"] = True
    elif case == "nonfinite_raw":
        response.selection_decision.selected_candidate.numerical_mapping["a"] = float("inf")
    elif case == "bool_evidence":
        link = replace(link, candidate_numeric=True)
    elif case == "nonfinite_evidence":
        link = replace(link, candidate_numeric=float("nan"))
    elif case == "bool_delivery":
        delivery.selected_candidate.numerical_mapping["a"] = True
    elif case == "nonfinite_delivery":
        delivery.selected_candidate.numerical_mapping["a"] = float("inf")
    elif case == "bool_ndigits":
        link = replace(link, decimal_places=True)
    elif case == "wrong_ndigits":
        link = replace(link, decimal_places=5)
    elif case == "wrong_transform":
        link = replace(link, delivery_transform="identity")
    elif case == "wrong_policy":
        link = replace(link, delivery_policy_id="projectile.general.time.round6")
    elif case == "wrong_raw_id":
        link = replace(link, candidate_id="raw:other")
    elif case == "wrong_raw_key_same_numeric":
        response.selection_decision.selected_candidate.numerical_mapping["N"] = raw
        link = replace(link, candidate_key="N")
    elif case == "wrong_raw_value":
        link = replace(link, candidate_numeric=raw + 1.0)
    elif case == "wrong_delivery_id":
        link = replace(link, delivery_candidate_id="delivery:other")
    elif case == "wrong_delivery_key":
        link = replace(link, delivery_candidate_key="normal_force")
    elif case == "wrong_delivery_value":
        delivery.selected_candidate.numerical_mapping["a"] = link.numeric + 1.0
    elif case == "same_id_does_not_imply_identity":
        delivery.selected_candidate.candidate_id = link.candidate_id
        link = replace(
            link,
            delivery_candidate_id=link.candidate_id,
            delivery_transform="identity",
            decimal_places=None,
            delivery_policy_id="",
        )
    elif case == "raw_ambiguous":
        response.selection_decision.status = "ambiguous"
    elif case == "raw_rejected":
        response.selection_decision.status = "no_valid_solution"
    elif case == "delivery_rejected":
        delivery.status = "no_valid_solution"
    elif case == "missing_delivery_decision":
        delivery = None

    evidence = replace(evidence, outputs=(link,))
    trace = _rebuild_raw_delivery(
        response, evidence, delivery, "constant_acceleration_1d"
    )
    expected_status = "ambiguous" if case == "raw_ambiguous" else "withheld"
    assert trace.status == expected_status
    assert trace.answer_derivation == []


@pytest.mark.unit
def test_duplicate_output_keys_require_unique_symbol_delivery_keys():
    answers = [
        _answer("friction_force", "f_s", 3.0, "N"),
        _answer("friction_force", "f_s,max", 5.0, "N"),
        _answer("normal_force", "N", 10.0, "N"),
    ]
    response = _response(answers)
    evidence = _evidence(answers)
    grounded = _build(response, _canonical(), evidence)
    assert grounded.status == "fully_grounded"
    assert [item.symbol for item in grounded.answer_derivation] == [
        "f_s",
        "f_s,max",
        "N",
    ]

    wrong = replace(
        evidence,
        outputs=(
            evidence.outputs[0],
            replace(
                evidence.outputs[1],
                candidate_key="friction_force",
                delivery_candidate_key="friction_force",
            ),
            evidence.outputs[2],
        ),
    )
    withheld = _build(response, _canonical(), wrong)
    assert withheld.status == "withheld"
    assert withheld.answer_derivation == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    ("same-key-reuse", "missing-key", "surplus-key", "cross-wire"),
)
def test_duplicate_output_group_rejects_non_bijective_delivery_keys(case):
    if case == "same-key-reuse":
        answers = [
            _answer("friction_force", "f_s", 3.0, "N"),
            _answer("friction_force", "f_s", 3.0, "N"),
        ]
    else:
        answers = [
            _answer("friction_force", "f_s", 3.0, "N"),
            _answer("friction_force", "f_s,max", 5.0, "N"),
        ]
    response = _response(answers)
    evidence = _evidence(answers)
    if case == "missing-key":
        evidence = replace(
            evidence,
            outputs=(
                evidence.outputs[0],
                replace(evidence.outputs[1], delivery_candidate_key=""),
            ),
        )
    elif case == "surplus-key":
        response.selection_decision.selected_candidate.numerical_mapping[
            "f_extra"
        ] = 5.0
    elif case == "cross-wire":
        first, second = evidence.outputs
        evidence = replace(
            evidence,
            outputs=(
                replace(
                    first,
                    candidate_key="f_s,max",
                    delivery_candidate_key="f_s,max",
                ),
                replace(
                    second,
                    candidate_key="f_s",
                    delivery_candidate_key="f_s",
                ),
            ),
        )

    trace = _build(response, _canonical(), evidence)
    assert trace.status == "withheld"
    assert trace.answer_derivation == []


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
def test_real_successful_migrated_solver_keeps_legacy_product_projection(
    problem_text, expected_solver, expected_equation
):
    response = services.solve_problem(problem_text)

    assert response.ok is True
    assert response.diagnosis.selected_solver == expected_solver
    assert response.answer is not None
    assert response.explanation_trace is not None
    assert response.explanation_trace.status == "fully_grounded"
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
    assert response.diagnosis.not_applicable_equations == ["legacy equation sentinel"]
    assert f"x = 530153 {_STALE_PUBLIC_SENTINEL}" in response.equation_sheet


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
        delivery_decision=response.selection_decision,
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
        delivery_decision=response.selection_decision,
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
        delivery_decision=response.selection_decision,
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
        delivery_decision=response.selection_decision,
    )

    assert [answer.model_dump() for answer in response.answers] == original_dump
    assert response.ok is True
    assert response.explanation_trace.status == "withheld"
    assert response.explanation_trace.answer_derivation == []
    assert "sensitive builder detail" not in response.explanation_trace.model_dump_json()
    _assert_scrubbed_public_physics(response, fully_grounded=False)
