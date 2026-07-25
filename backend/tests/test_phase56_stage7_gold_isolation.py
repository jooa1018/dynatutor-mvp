"""Stage 7 gold/runtime isolation attack suite.

Each test is an attempted leak or an attempted routing shortcut.  All of them
must fail closed, and a deterministic runtime must produce a bit-identical
result no matter what the gold domain knows about the case.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.phase56_stage7.contracts import (
    Stage7ExpectedTerminal,
    Stage7RuntimeTerminal,
)
from evaluation.phase56_stage7.corpus_records import (
    CorpusFactV1,
    CorpusReferenceAnswerV1,
    PublicCorpusCaseV1,
)
from evaluation.phase56_stage7.evaluator_adapter import (
    ExecutionTokenIssuer,
    GoldIsolationViolation,
    assert_gold_domain_has_no_execution_authority,
    assert_runtime_material_is_gold_free,
    rebind_after_freeze,
    to_runtime_input,
)
from evaluation.phase56_stage7.gold_domain import (
    FrozenRuntimeResultV1,
    GoldDomainCaseV1,
    GoldNumericAnswerV1,
    PublicSplit,
)
from evaluation.phase56_stage7.isolation import assert_production_runtime_isolated
from evaluation.phase56_stage7.runtime_domain import (
    RuntimeAnswerV1,
    RuntimeDomainSnapshotV1,
    RuntimeEvaluationMode,
    RuntimeOptionsV1,
    build_typed_runtime_input,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

PROBLEM_TEXT = (
    "수평면 위의 물체에서 질량은 2.0 kg 이고 가속도는 3.0 m/s^2 이다. 알짜힘을 구하시오."
)
PROBLEM_SHA256 = hashlib.sha256(PROBLEM_TEXT.encode("utf-8")).hexdigest()


def _options() -> RuntimeOptionsV1:
    return RuntimeOptionsV1(mechanics_mode=RuntimeEvaluationMode.required)


def _corpus_case(**overrides) -> PublicCorpusCaseV1:
    base = {
        "case_id": "public_dev-0001",
        "split": PublicSplit.public_dev,
        "family": "newton_second_law",
        "problem_text": PROBLEM_TEXT,
        "problem_sha256": PROBLEM_SHA256,
        "evidence_quotes": ("질량은 2.0 kg", "가속도는 3.0 m/s^2"),
        "facts": (
            CorpusFactV1(role="mass", value=2.0, unit="kg"),
            CorpusFactV1(role="acceleration", value=3.0, unit="m/s^2"),
        ),
        "reference_answer": CorpusReferenceAnswerV1(value=6.0, unit="N"),
        "declared_terminal": "accepted",
        "chapter": "ch12",
    }
    base.update(overrides)
    return PublicCorpusCaseV1(**base)


def _deterministic_runtime(runtime_input) -> RuntimeDomainSnapshotV1:
    """A stand-in runtime whose only input is the runtime-domain input."""

    digest = runtime_input.cache_sha256()
    return RuntimeDomainSnapshotV1(
        execution_token=runtime_input.execution_token,
        input_cache_sha256=digest,
        terminal=Stage7RuntimeTerminal.solved,
        answer=RuntimeAnswerV1(value=6.0, unit="N"),
        calculation_fingerprint=digest,
        equation_graph_fingerprint=digest,
        solve_plan_fingerprint=digest,
        candidate_set_fingerprint=digest,
        verification_fingerprint=digest,
        candidate_count=1,
        verified_candidate_count=1,
        runtime_call_count=1,
        compiler_call_count=1,
        solver_call_count=1,
        model_or_provider_call_count=0,
    )


# --------------------------------------------------------------------------
# Forbidden fields, directly and nested
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "case_id",
        "corpus_family",
        "split",
        "expected_terminal",
        "expected_answer",
        "gold_graph",
        "tolerance",
        "chapter",
        "tags",
        "difficulty",
        "failure_label",
        "selected_solver",
        "selected_root",
        "verification_result",
        "file_path",
    ),
)
def test_direct_forbidden_field_is_rejected(forbidden_key: str) -> None:
    with pytest.raises(ValidationError, match="forbidden metadata key"):
        build_typed_runtime_input(
            execution_token="a" * 32,
            payload={"entities": [], forbidden_key: "leak"},
            options=_options(),
        )


@pytest.mark.parametrize(
    "forbidden_key",
    ("case_id", "family", "expected_answer", "gold_graph", "expected_terminal"),
)
def test_nested_forbidden_field_is_rejected_at_depth(forbidden_key: str) -> None:
    payload = {
        "entities": [
            {
                "entity_id": "bodyA",
                "annotations": [{"provenance": {forbidden_key: "leak"}}],
            }
        ]
    }
    with pytest.raises(ValidationError, match="forbidden metadata key"):
        build_typed_runtime_input(
            execution_token="a" * 32, payload=payload, options=_options()
        )


@pytest.mark.parametrize(
    "alias", ("caseId", "case-id", "CASE ID", "Corpus Family", "expected-answer")
)
def test_alias_spellings_of_forbidden_fields_are_rejected(alias: str) -> None:
    with pytest.raises(ValidationError, match="forbidden metadata key"):
        build_typed_runtime_input(
            execution_token="a" * 32,
            payload={"entities": [], alias: "leak"},
            options=_options(),
        )


# --------------------------------------------------------------------------
# Routing attacks
# --------------------------------------------------------------------------


def test_case_id_routing_cannot_change_a_deterministic_result() -> None:
    issuer = ExecutionTokenIssuer(run_nonce="stage7-isolation")
    baseline_case = _corpus_case()
    renamed_case = _corpus_case(case_id="zzz-completely-different-9999")

    baseline = to_runtime_input(
        baseline_case, execution_token=issuer.issue(0), options=_options()
    )
    renamed = to_runtime_input(
        renamed_case, execution_token=issuer.issue(1), options=_options()
    )

    assert baseline.execution_token != renamed.execution_token
    assert baseline.cache_sha256() == renamed.cache_sha256()
    assert _deterministic_runtime(baseline).input_cache_sha256 == (
        _deterministic_runtime(renamed).input_cache_sha256
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("family", "spring_mass_vibration"),
        ("split", PublicSplit.public_adversarial),
        ("chapter", "ch99"),
        ("declared_terminal", "needs_figure"),
        ("problem_sha256", "f" * 64),
    ),
)
def test_family_split_chapter_and_terminal_routing_cannot_reach_runtime(
    field: str, value: object
) -> None:
    token = ExecutionTokenIssuer(run_nonce="stage7-isolation").issue(0)
    baseline = to_runtime_input(
        _corpus_case(), execution_token=token, options=_options()
    )
    rerouted = to_runtime_input(
        _corpus_case(**{field: value}), execution_token=token, options=_options()
    )
    assert baseline == rerouted
    assert baseline.cache_material() == rerouted.cache_material()


def test_expected_answer_lookup_cannot_reach_runtime_or_cache() -> None:
    token = ExecutionTokenIssuer(run_nonce="stage7-isolation").issue(0)
    baseline = to_runtime_input(
        _corpus_case(), execution_token=token, options=_options()
    )
    rewritten = to_runtime_input(
        _corpus_case(
            reference_answer=CorpusReferenceAnswerV1(value=999999.5, unit="kg")
        ),
        execution_token=token,
        options=_options(),
    )
    assert baseline.cache_material() == rewritten.cache_material()
    assert b"999999.5" not in baseline.cache_material()


def test_adapter_emits_no_gold_token_into_runtime_material() -> None:
    case = _corpus_case()
    token = ExecutionTokenIssuer(run_nonce="stage7-isolation").issue(0)
    runtime_input = to_runtime_input(case, execution_token=token, options=_options())
    assert_runtime_material_is_gold_free(runtime_input, case)
    serialized = runtime_input.model_dump_json()
    for leaked in ("public_dev-0001", "newton_second_law", "ch12", PROBLEM_SHA256):
        assert leaked not in serialized


def test_filename_and_path_routing_is_not_expressible() -> None:
    for key in ("filename", "file_path", "zip_entry_path", "source_path"):
        payload = {"entities": [], key: "public_adversarial.jsonl"}
        if key in ("filename", "file_path"):
            with pytest.raises(ValidationError, match="forbidden metadata key"):
                build_typed_runtime_input(
                    execution_token="a" * 32, payload=payload, options=_options()
                )
        else:
            # Names outside the forbidden catalogue are still inert: they cannot
            # change cache identity relative to the same payload without them.
            with_path = build_typed_runtime_input(
                execution_token="a" * 32, payload=payload, options=_options()
            )
            without_path = build_typed_runtime_input(
                execution_token="a" * 32, payload={"entities": []}, options=_options()
            )
            assert with_path.cache_sha256() != without_path.cache_sha256()


# --------------------------------------------------------------------------
# Cache, prompt, and environment contamination
# --------------------------------------------------------------------------


def test_cache_identity_excludes_the_opaque_token_but_covers_real_input() -> None:
    issuer = ExecutionTokenIssuer(run_nonce="stage7-isolation")
    first = to_runtime_input(
        _corpus_case(), execution_token=issuer.issue(0), options=_options()
    )
    second = to_runtime_input(
        _corpus_case(), execution_token=issuer.issue(1), options=_options()
    )
    assert first.execution_token != second.execution_token
    assert first.cache_sha256() == second.cache_sha256()

    changed_text = to_runtime_input(
        _corpus_case(
            problem_text=PROBLEM_TEXT.replace("3.0 m/s^2", "4.0 m/s^2"),
            problem_sha256=hashlib.sha256(
                PROBLEM_TEXT.replace("3.0 m/s^2", "4.0 m/s^2").encode("utf-8")
            ).hexdigest(),
            evidence_quotes=("질량은 2.0 kg", "가속도는 4.0 m/s^2"),
        ),
        execution_token=issuer.issue(2),
        options=_options(),
    )
    assert changed_text.cache_sha256() != first.cache_sha256()


def test_prompt_material_is_exactly_the_user_like_input() -> None:
    case = _corpus_case()
    runtime_input = to_runtime_input(
        case,
        execution_token=ExecutionTokenIssuer(run_nonce="n").issue(0),
        options=_options(),
    )
    payload = json.loads(runtime_input.cache_material())
    assert payload["problem_text"] == PROBLEM_TEXT
    assert payload["typed_input"] is None
    assert payload["images"] == []
    assert set(payload) == {
        "schema",
        "version",
        "input_kind",
        "problem_text",
        "typed_input",
        "images",
        "options",
    }


def test_environment_contamination_cannot_change_runtime_input(monkeypatch) -> None:
    case = _corpus_case()
    token = ExecutionTokenIssuer(run_nonce="n").issue(0)
    baseline = to_runtime_input(case, execution_token=token, options=_options())
    for name, value in (
        ("STAGE7_CASE_ID", case.case_id),
        ("STAGE7_FAMILY", case.family),
        ("STAGE7_EXPECTED_ANSWER", "6.0"),
        ("STAGE7_EXPECTED_TERMINAL", "solved"),
        ("STAGE7_SPLIT", case.split.value),
    ):
        monkeypatch.setenv(name, value)
    contaminated = to_runtime_input(case, execution_token=token, options=_options())
    assert contaminated == baseline
    assert contaminated.cache_sha256() == baseline.cache_sha256()
    assert _deterministic_runtime(contaminated) == _deterministic_runtime(baseline)


# --------------------------------------------------------------------------
# Freeze-then-score boundary
# --------------------------------------------------------------------------


def test_scoring_rebinds_only_after_the_snapshot_is_frozen() -> None:
    case = _corpus_case()
    token = ExecutionTokenIssuer(run_nonce="n").issue(0)
    runtime_input = to_runtime_input(case, execution_token=token, options=_options())
    snapshot = _deterministic_runtime(runtime_input)
    frozen, bound = rebind_after_freeze(
        snapshot=snapshot, runtime_input=runtime_input, cases_by_token={token: case}
    )
    assert isinstance(frozen, FrozenRuntimeResultV1)
    assert bound.case_id == case.case_id
    with pytest.raises(ValidationError, match="frozen"):
        frozen.snapshot.terminal = Stage7RuntimeTerminal.runtime_failure


def test_substituted_execution_cannot_be_rebound() -> None:
    case = _corpus_case()
    issuer = ExecutionTokenIssuer(run_nonce="n")
    runtime_input = to_runtime_input(
        case, execution_token=issuer.issue(0), options=_options()
    )
    other_input = to_runtime_input(
        _corpus_case(problem_text="다른 문제입니다. 속도를 구하시오."),
        execution_token=issuer.issue(1),
        options=_options(),
    )
    foreign_snapshot = _deterministic_runtime(other_input)
    with pytest.raises(ValueError, match="token does not match"):
        rebind_after_freeze(
            snapshot=foreign_snapshot,
            runtime_input=runtime_input,
            cases_by_token={runtime_input.execution_token: case},
        )


def test_unbound_token_cannot_be_scored() -> None:
    case = _corpus_case()
    runtime_input = to_runtime_input(
        case,
        execution_token=ExecutionTokenIssuer(run_nonce="n").issue(0),
        options=_options(),
    )
    with pytest.raises(GoldIsolationViolation, match="no gold case is bound"):
        rebind_after_freeze(
            snapshot=_deterministic_runtime(runtime_input),
            runtime_input=runtime_input,
            cases_by_token={},
        )


def test_gold_case_cannot_carry_an_answer_for_a_blocked_terminal() -> None:
    with pytest.raises(ValidationError, match="non-accepted"):
        GoldDomainCaseV1(
            case_id="public-x",
            split=PublicSplit.public_adversarial,
            family="newton_second_law",
            problem_sha256="1" * 64,
            expected_terminal=Stage7ExpectedTerminal.needs_figure,
            expected_answer=GoldNumericAnswerV1(
                value=1.0, unit="N", absolute_tolerance=0.0, relative_tolerance=0.0
            ),
        )


# --------------------------------------------------------------------------
# Structural authority boundaries
# --------------------------------------------------------------------------


def test_production_modules_cannot_import_the_evaluator() -> None:
    assert_production_runtime_isolated(REPOSITORY_ROOT)


def test_gold_domain_modules_have_no_production_answer_authority() -> None:
    assert_gold_domain_has_no_execution_authority(REPOSITORY_ROOT)


def test_runtime_domain_module_never_imports_gold_or_corpus_modules() -> None:
    source = (
        REPOSITORY_ROOT / "backend/evaluation/phase56_stage7/runtime_domain.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("gold_domain", "corpus_records", "corpus_semantics", "corpus_integrity"):
        assert forbidden not in source
