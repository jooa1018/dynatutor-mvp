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
    ValidatedCandidateModel,
    VerificationReport as VerificationReportModel,
)
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


def _fixture():
    canonical = CanonicalProblem(
        system_type="synthetic_force",
        knowns={
            "F": Quantity("F", 10.0, "N"),
            "m": Quantity("m", 2.0, "kg"),
        },
    )
    answer = AnswerItemModel(
        label="가속도",
        symbol="a",
        numeric=5.0,
        unit="m/s^2",
        display="5 m/s^2",
        role="primary",
        output_key="acceleration",
    )
    selected = CandidateSolutionModel(
        candidate_id="candidate:selected:hidden",
        numerical_mapping={"a": 5.0, "acceleration": 5.0},
    )
    rejected = ValidatedCandidateModel(
        candidate_id="candidate:rejected:hidden",
        numerical_mapping={"acceleration": 987654.0},
        accepted=False,
        rejection_reasons=["violates event condition"],
    )
    response = SolveResponse(
        ok=True,
        diagnosis=DiagnosisResponse(
            ok=True,
            canonical=CanonicalProblemModel(system_type="synthetic_force"),
            legacy_hints=LegacyHintModel(),
            selected_solver="solver:hidden",
            solver_reason="synthetic",
        ),
        answers=[answer],
        verification=VerificationReportModel(passed=True),
        selection_decision=SelectionDecisionModel(
            status="selected",
            selected_candidate=selected,
            rejected_candidates=[rejected],
            selection_policy="exact",
            explanation="selected exact output",
            policy_version="phase53-test",
        ),
    )
    evidence = SolverExplanationEvidence(
        coordinate_frame=CalculationCoordinateFrame(
            frame_id="frame:hidden",
            coordinate_system="cartesian_1d",
            axes=("x",),
            positive_directions=("right",),
            source="solver_calculation",
            status="resolved",
        ),
        explicit_facts=(
            SemanticFactEvidence("known:F", "F", 10.0, "N"),
            SemanticFactEvidence("known:m", "m", 2.0, "kg"),
        ),
        equations=(
            EquationEvidence(
                "eq:hidden",
                "a = F / m",
                "solver_equation",
                "newton_second_law",
                fact_ids=("known:F", "known:m"),
                output_ids=("output:hidden",),
            ),
        ),
        substitutions=(
            SubstitutionEvidence(
                "sub:hidden",
                "eq:hidden",
                "a = 10 / 2 = 5 m/s^2",
                "output:hidden",
                fact_ids=("known:F", "known:m"),
            ),
        ),
        outputs=(
            OutputEvidenceLink(
                "output:hidden",
                "acceleration",
                "candidate:selected:hidden",
                5.0,
                "m/s^2",
                symbol="a",
                role="primary",
                response_index=0,
                equation_ids=("eq:hidden",),
                substitution_ids=("sub:hidden",),
                candidate_key="a",
                candidate_numeric=5.0,
                delivery_candidate_id="candidate:selected:hidden",
                delivery_candidate_key="a",
                delivery_transform="identity",
            ),
        ),
    )
    return canonical, response, evidence


def _build(canonical, response, evidence, *, route_status="select"):
    return ExplanationTraceModel(
        **build_explanation_trace_payload(
            response=response,
            canonical=canonical,
            physical_model={},
            result=SolverResult(ok=response.ok, explanation_evidence=evidence),
            selected_solver="solver:hidden",
            route_reason="synthetic",
            route_decision=SimpleNamespace(status=route_status, warnings=[]),
            delivery_decision=response.selection_decision,
        )
    )


def _with_linked_facts(
    evidence,
    *,
    explicit_facts=(),
    assumptions=(),
):
    """Attach synthetic facts to every dependency edge in the one-output fixture."""

    fact_ids = tuple(fact.fact_id for fact in (*explicit_facts, *assumptions))
    equation = replace(
        evidence.equations[0],
        fact_ids=evidence.equations[0].fact_ids + fact_ids,
    )
    substitution = replace(
        evidence.substitutions[0],
        fact_ids=evidence.substitutions[0].fact_ids + fact_ids,
    )
    return replace(
        evidence,
        explicit_facts=evidence.explicit_facts + tuple(explicit_facts),
        assumptions=evidence.assumptions + tuple(assumptions),
        equations=(equation,),
        substitutions=(substitution,),
    )


def _student_projection_dump(response) -> str:
    diagnosis = response.diagnosis
    return json.dumps(
        {
            "teacher_summary": response.teacher_summary,
            "concept_summary": response.concept_summary,
            "common_mistakes": response.common_mistakes,
            "study_tips": response.study_tips,
            "equation_sheet": response.equation_sheet,
            "steps": [step.model_dump() for step in response.steps],
            "fbd_diagram_svg": diagnosis.fbd_diagram_svg,
            "fbd_annotations": diagnosis.fbd_annotations,
            "fbd": diagnosis.fbd,
            "coordinate_guide": diagnosis.coordinate_guide,
            "applicable_equations": diagnosis.applicable_equations,
            "not_applicable_equations": diagnosis.not_applicable_equations,
            "cautions": diagnosis.cautions,
            "next_questions": diagnosis.next_questions,
            "legacy_hints": diagnosis.legacy_hints.model_dump(),
            "diagnosis_physical_model": diagnosis.physical_model,
            "physical_model": response.physical_model,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@pytest.mark.unit
def test_code_owned_subtype_flag_branch_assumption_and_units_can_fully_ground():
    canonical, response, evidence = _fixture()
    canonical = replace(
        canonical,
        system_type="vertical_circle",
        subtype="top",
        launch_height=3.0,
        flags={"starts_from_rest": True},
    )
    subtype = SemanticFactEvidence(
        "semantic:subtype",
        "subtype",
        "top",
        source="canonical_semantic",
        classification="explicit",
    )
    height = SemanticFactEvidence(
        "semantic:launch_height",
        "launch_height",
        3.0,
        "m",
        source="canonical_semantic",
        classification="explicit",
    )
    flag = SemanticFactEvidence(
        "flag:starts_from_rest",
        "starts_from_rest",
        True,
        source="canonical_flag",
        classification="explicit",
    )
    branch = SemanticFactEvidence(
        "branch:event_condition",
        "event_condition",
        "at_event",
        source="solver_branch_explicit",
        classification="branch_condition",
    )
    assumption = SemanticFactEvidence(
        "assumption:air_resistance",
        "air_resistance",
        "ignored",
        source="solver_assumption",
        classification="assumed",
    )
    evidence = _with_linked_facts(
        evidence,
        explicit_facts=(subtype, height, flag, branch),
        assumptions=(assumption,),
    )

    trace = _build(canonical, response, evidence)

    assert trace.status == "fully_grounded"
    assert {fact.fact_id for fact in trace.explicit_facts} >= {
        "semantic:subtype",
        "semantic:launch_height",
        "flag:starts_from_rest",
        "branch:event_condition",
    }
    assert [(fact.semantic_key, fact.value, fact.unit) for fact in trace.assumptions] == [
        ("air_resistance", "ignored", None)
    ]
    assert trace.answer_derivation[0].unit == "m/s^2"


@pytest.mark.unit
@pytest.mark.parametrize(
    "subtype_value",
    [
        "arbitrary_technical_token",
        "top\nstudent_solution",
        "x" * 500,
    ],
)
def test_allowlisted_subtype_key_rejects_non_registry_values(subtype_value):
    canonical, response, evidence = _fixture()
    canonical = replace(
        canonical,
        system_type="vertical_circle",
        subtype=subtype_value,
    )
    fact = SemanticFactEvidence(
        "semantic:subtype",
        "subtype",
        subtype_value,
        source="canonical_semantic",
        classification="explicit",
    )
    evidence = _with_linked_facts(evidence, explicit_facts=(fact,))
    original_answers = [answer.model_dump() for answer in response.answers]

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert subtype_value not in trace.model_dump_json()
    assert subtype_value not in _student_projection_dump(response)
    assert [answer.model_dump() for answer in response.answers] == original_answers


@pytest.mark.unit
def test_code_owned_subtype_is_rejected_for_the_wrong_system_type():
    canonical, response, evidence = _fixture()
    canonical = replace(
        canonical,
        system_type="particle_on_incline",
        subtype="top",
    )
    fact = SemanticFactEvidence(
        "semantic:subtype",
        "subtype",
        "top",
        source="canonical_semantic",
        classification="explicit",
    )
    evidence = _with_linked_facts(evidence, explicit_facts=(fact,))

    trace = _build(canonical, response, evidence)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert all(
        item.fact_id != "semantic:subtype" for item in trace.explicit_facts
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("namespace", "bad_value"),
    [
        ("branch", True),
        ("branch", 1.0),
        ("assumption", False),
        ("assumption", 0.0),
    ],
)
def test_branch_and_assumption_enums_reject_bool_and_numeric_bypass(
    namespace, bad_value
):
    canonical, response, evidence = _fixture()
    if namespace == "branch":
        fact = SemanticFactEvidence(
            "branch:event_condition",
            "event_condition",
            bad_value,
            source="solver_branch_explicit",
            classification="branch_condition",
        )
        evidence = _with_linked_facts(evidence, explicit_facts=(fact,))
    else:
        fact = SemanticFactEvidence(
            "assumption:air_resistance",
            "air_resistance",
            bad_value,
            source="solver_assumption",
            classification="assumed",
        )
        evidence = _with_linked_facts(evidence, assumptions=(fact,))

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert fact.fact_id not in {
        item.fact_id for item in (*trace.explicit_facts, *trace.assumptions)
    }
    assert all(
        step.kind not in {"equation", "substitution", "answer"}
        for step in trace.student_steps
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "unit_sentinel",
    [
        "arbitrary_technical_unit",
        "source_text",
        "N\nstudent_solution",
        "u" * 500,
    ],
)
def test_known_fact_rejects_non_physical_control_and_oversized_units(unit_sentinel):
    canonical, response, evidence = _fixture()
    canonical.knowns["F"] = Quantity("F", 10.0, unit_sentinel)
    poisoned_fact = replace(evidence.explicit_facts[0], unit=unit_sentinel)
    evidence = replace(
        evidence,
        explicit_facts=(poisoned_fact, evidence.explicit_facts[1]),
    )
    original_answers = [answer.model_dump() for answer in response.answers]

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert unit_sentinel not in trace.model_dump_json()
    assert unit_sentinel not in _student_projection_dump(response)
    assert [answer.model_dump() for answer in response.answers] == original_answers


@pytest.mark.unit
def test_semantic_numeric_fact_rejects_arbitrary_unit_even_when_value_is_valid():
    canonical, response, evidence = _fixture()
    canonical = replace(canonical, launch_height=3.0)
    marker = "launch_height_unit_sentinel"
    fact = SemanticFactEvidence(
        "semantic:launch_height",
        "launch_height",
        3.0,
        marker,
        source="canonical_semantic",
        classification="explicit",
    )
    evidence = _with_linked_facts(evidence, explicit_facts=(fact,))

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert marker not in trace.model_dump_json()
    assert marker not in _student_projection_dump(response)


@pytest.mark.unit
@pytest.mark.parametrize("case", ["unlinked_equation", "unlinked_fact", "unlinked_output"])
def test_unlinked_structured_evidence_cannot_be_fully_grounded(case):
    canonical, response, evidence = _fixture()
    if case == "unlinked_equation":
        evidence = replace(
            evidence,
            equations=evidence.equations
            + (
                EquationEvidence(
                    "eq:orphan",
                    "z = F",
                    "solver_equation",
                    "synthetic",
                    fact_ids=("known:F",),
                    output_ids=("orphan:output",),
                ),
            ),
        )
    elif case == "unlinked_fact":
        evidence = replace(
            evidence,
            explicit_facts=evidence.explicit_facts
            + (
                SemanticFactEvidence(
                    "branch:orphan",
                    "event_condition",
                    "after impact",
                    source="solver_branch_explicit",
                    classification="branch_condition",
                ),
            ),
        )
    else:
        evidence = replace(
            evidence,
            outputs=evidence.outputs
            + (
                OutputEvidenceLink(
                    "output:orphan",
                    "velocity",
                    "candidate:selected:hidden",
                    99.0,
                    "m/s",
                    equation_ids=("eq:hidden",),
                    substitution_ids=("sub:hidden",),
                ),
            ),
        )

    trace = _build(canonical, response, evidence)

    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    assert all(step.kind not in {"equation", "substitution", "answer"} for step in trace.student_steps)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("injected_fact", "marker"),
    [
        (
            SemanticFactEvidence(
                "branch:raw_text", "raw_text", True,
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "raw_text",
        ),
        (
            SemanticFactEvidence(
                "branch:source_text", "source_text", True,
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "source_text",
        ),
        (
            SemanticFactEvidence(
                "branch:student_solution", "student_solution", True,
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "student_solution",
        ),
        (
            SemanticFactEvidence(
                "branch:problem_text", "problem_text", True,
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "problem_text",
        ),
        (
            SemanticFactEvidence(
                "branch:unapproved_semantic_key", "unapproved_semantic_key", True,
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "unapproved_semantic_key",
        ),
        (
            SemanticFactEvidence(
                "known:F", "F", 10.0, "N",
                source="evil_source", classification="explicit",
            ),
            "evil_source",
        ),
        (
            SemanticFactEvidence(
                "branch:event_condition", "event_condition",
                "raw sentence payload must not project",
                source="solver_branch_explicit", classification="branch_condition",
            ),
            "raw sentence payload must not project",
        ),
    ],
)
def test_structured_fact_allowlist_rejects_text_and_arbitrary_categories(
    injected_fact, marker
):
    canonical, response, evidence = _fixture()
    evidence = replace(
        evidence,
        explicit_facts=evidence.explicit_facts + (injected_fact,),
    )

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert marker not in trace.model_dump_json()
    assert marker not in _student_projection_dump(response)


@pytest.mark.unit
@pytest.mark.parametrize(
    "forbidden_value",
    ["raw_text", "source_text", "student_solution", "problem_text"],
)
def test_allowlisted_branch_key_rejects_forbidden_string_value(forbidden_value):
    canonical, response, evidence = _fixture()
    injected = SemanticFactEvidence(
        "branch:event_condition",
        "event_condition",
        forbidden_value,
        source="solver_branch_explicit",
        classification="branch_condition",
    )
    evidence = replace(
        evidence,
        explicit_facts=evidence.explicit_facts + (injected,),
    )

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert forbidden_value not in trace.model_dump_json()
    assert forbidden_value not in _student_projection_dump(response)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("replacement", "marker"),
    [
        ({"coordinate_system": "raw_text"}, "raw_text"),
        (
            {"coordinate_system": "free coordinate system sentence"},
            "free coordinate system sentence",
        ),
        ({"axes": ("student_solution",)}, "student_solution"),
        ({"axes": ("free axis sentence",)}, "free axis sentence"),
        ({"positive_directions": ("problem_text",)}, "problem_text"),
        (
            {"positive_directions": ("free direction sentence",)},
            "free direction sentence",
        ),
        ({"units": ("source_text",)}, "source_text"),
        ({"units": ("free unit sentence",)}, "free unit sentence"),
        ({"source": "student_solution"}, "student_solution"),
    ],
)
def test_calculation_coordinate_boundary_rejects_text_and_forbidden_categories(
    replacement, marker
):
    canonical, response, evidence = _fixture()
    evidence = replace(
        evidence,
        coordinate_frame=replace(evidence.coordinate_frame, **replacement),
    )

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.coordinate_frame is None
    assert marker not in trace.model_dump_json()
    assert marker not in _student_projection_dump(response)


@pytest.mark.unit
def test_free_form_canonical_assumption_is_omitted_and_prevents_full_grounding():
    canonical, response, evidence = _fixture()
    marker = "FREE FORM ASSUMPTION SENTINEL 5302"
    canonical.assumptions = [marker]

    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status != "fully_grounded"
    assert trace.assumptions == []
    assert marker not in trace.model_dump_json()
    assert marker not in _student_projection_dump(response)


@pytest.mark.unit
@pytest.mark.parametrize(
    "replacement",
    [
        {"numeric": -5.0},
        {"unit": "km/s^2"},
        {"output_key": "velocity"},
        {"candidate_id": "candidate:rejected:hidden"},
        {"equation_ids": ()},
        {"substitution_ids": ()},
    ],
)
def test_mismatched_output_contract_withholds_derivation(replacement):
    canonical, response, evidence = _fixture()
    evidence = replace(
        evidence,
        outputs=(replace(evidence.outputs[0], **replacement),),
    )

    trace = _build(canonical, response, evidence)

    assert trace.status == "withheld"
    assert trace.answer_derivation == []
    assert trace.warnings


def _multi_fixture():
    canonical, response, evidence = _fixture()
    second_answer = AnswerItemModel(
        label="속도",
        symbol="v",
        numeric=7.0,
        unit="m/s",
        display="7 m/s",
        role="primary",
        output_key="final_velocity",
    )
    response.answers.append(second_answer)
    response.selection_decision.selected_candidate.numerical_mapping["v"] = 7.0
    response.selection_decision.selected_candidate.numerical_mapping["final_velocity"] = 7.0
    second_equation = EquationEvidence(
        "eq:velocity:hidden",
        "v = F - 3",
        "solver_equation",
        "solver_derived",
        fact_ids=("known:F", "known:m"),
        output_ids=("output:velocity:hidden",),
    )
    second_substitution = SubstitutionEvidence(
        "sub:velocity:hidden",
        "eq:velocity:hidden",
        "v = 10 - 3 = 7 m/s",
        "output:velocity:hidden",
        fact_ids=("known:F", "known:m"),
    )
    second_output = OutputEvidenceLink(
        "output:velocity:hidden",
        "final_velocity",
        "candidate:selected:hidden",
        7.0,
        "m/s",
        symbol="v",
        role="primary",
        response_index=1,
        equation_ids=("eq:velocity:hidden",),
        substitution_ids=("sub:velocity:hidden",),
        candidate_key="v",
        candidate_numeric=7.0,
        delivery_candidate_id="candidate:selected:hidden",
        delivery_candidate_key="v",
        delivery_transform="identity",
    )
    evidence = replace(
        evidence,
        equations=evidence.equations + (second_equation,),
        substitutions=evidence.substitutions + (second_substitution,),
        outputs=evidence.outputs + (second_output,),
    )
    return canonical, response, evidence


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    [
        "swapped_equations",
        "duplicate_output_id",
        "reused_substitution",
        "equation_output_mismatch",
    ],
)
def test_multi_answer_output_dependency_closure_rejects_cross_wiring(case):
    canonical, response, evidence = _multi_fixture()
    first, second = evidence.outputs
    if case == "swapped_equations":
        evidence = replace(
            evidence,
            outputs=(
                replace(first, equation_ids=second.equation_ids),
                replace(second, equation_ids=first.equation_ids),
            ),
        )
    elif case == "duplicate_output_id":
        evidence = replace(
            evidence,
            outputs=(first, replace(second, output_id=first.output_id)),
        )
    elif case == "reused_substitution":
        evidence = replace(
            evidence,
            outputs=(
                first,
                replace(
                    second,
                    equation_ids=first.equation_ids,
                    substitution_ids=first.substitution_ids,
                ),
            ),
        )
    else:
        evidence = replace(
            evidence,
            equations=(
                evidence.equations[0],
                replace(
                    evidence.equations[1],
                    output_ids=("output:wrong:hidden",),
                ),
            ),
        )

    trace = _build(canonical, response, evidence)

    assert trace.status == "withheld"
    assert trace.answer_derivation == []
    assert any(
        token in " ".join(trace.warnings)
        for token in ("unique", "reuses", "swapped", "declared", "produced")
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("terminal_status", "route_status", "error"),
    [
        ("ambiguous", "clarify", None),
        ("unsupported", "unsupported", None),
        ("contradictory", "select", "contradictory explicit inputs"),
    ],
)
def test_nondefinitive_terminal_states_have_neutral_projection(
    terminal_status, route_status, error
):
    canonical, response, evidence = _fixture()
    response.ok = False
    response.verification.passed = False
    if error:
        response.verification.errors.append(error)

    trace = _build(canonical, response, evidence, route_status=route_status)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.status == terminal_status
    assert trace.answer_derivation == []
    projected = json.dumps(
        {
            "steps": [step.model_dump() for step in response.steps],
            "teacher": response.teacher_summary,
            "concept": response.concept_summary,
            "mistakes": response.common_mistakes,
            "equations": response.equation_sheet,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "5 m/s^2" not in projected
    assert "987654" not in projected
    assert "eq:hidden" not in projected
    assert "candidate:" not in projected
    assert response.equation_sheet == []


@pytest.mark.unit
def test_rejected_candidate_values_never_enter_trace_or_student_text():
    canonical, response, evidence = _fixture()
    trace = _build(canonical, response, evidence)
    response.explanation_trace = trace
    project_explanation_from_trace(response)

    assert trace.candidate_summary.rejected_count == 1
    assert "987654" not in trace.model_dump_json()
    assert "987654" not in json.dumps(
        [step.model_dump() for step in response.steps], ensure_ascii=False
    )
