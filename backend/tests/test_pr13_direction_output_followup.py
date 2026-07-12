from __future__ import annotations

import json
import math

import pytest

from app.routes import records as records_route
from app.schemas.records import RecordCreate
from engine.models import AnswerItem
from engine.physics_core.answer_validators import validate_answer_consistency
from engine.physics_core.coordinate_parser import parse_coordinate_data_from_text
from engine.services import solve_problem
from engine.storage import notebook


def _signs(text: str) -> dict[str, float]:
    return parse_coordinate_data_from_text(text).values


def test_attached_cw_korean_suffix():
    assert _signs("omega=2rad/s cw방향")["omega_sign"] == -1.0


def test_attached_ccw_korean_suffix():
    assert _signs("omega=2rad/s ccw방향")["omega_sign"] == 1.0


def test_counter_hyphen_clockwise_is_positive():
    assert _signs("omega is counter-clockwise")["omega_sign"] == 1.0


def test_counter_space_clockwise_is_positive():
    assert _signs("omega is counter clockwise")["omega_sign"] == 1.0


def test_initial_angular_velocity_without_space_does_not_bind_omega():
    parsed = _signs("초기각속도는 시계방향이다.")

    assert parsed["omega0_sign"] == -1.0
    assert "omega_sign" not in parsed


@pytest.mark.parametrize("spaces", ["", " ", "  "])
def test_initial_angular_velocity_spacing_does_not_bind_omega(spaces: str):
    parsed = _signs(f"초기{spaces}각속도는 시계방향이다.")

    assert parsed["omega0_sign"] == -1.0
    assert "omega_sign" not in parsed


def test_initial_and_current_angular_velocity_directions_are_independent():
    parsed = _signs(
        "초기각속도는 시계방향이고 각속도는 반시계방향이다."
    )

    assert parsed["omega0_sign"] == -1.0
    assert parsed["omega_sign"] == 1.0


def test_english_initial_and_current_angular_velocity_are_independent():
    parsed = _signs(
        "omega0 is counter-clockwise and omega is clockwise"
    )

    assert parsed["omega0_sign"] == 1.0
    assert parsed["omega_sign"] == -1.0


def _report(requested: str, item: AnswerItem):
    return validate_answer_consistency(
        ok=True,
        answer=None,
        answers=[item],
        requested_outputs=[requested],
    )


def test_angular_velocity_does_not_satisfy_angular_frequency():
    item = AnswerItem(
        label="각속도",
        symbol="omega",
        numeric=2.0,
        unit="rad/s",
        display="omega = 2 rad/s",
        output_key="angular_velocity",
    )

    assert not _report("angular_frequency", item).passed


def test_angular_frequency_does_not_satisfy_angular_velocity():
    item = AnswerItem(
        label="고유각진동수",
        symbol="omega",
        numeric=2.0,
        unit="rad/s",
        display="omega = 2 rad/s",
        output_key="angular_frequency",
    )

    assert not _report("angular_velocity", item).passed


def test_omega_n_still_satisfies_angular_frequency():
    item = AnswerItem(
        label="고유각진동수",
        symbol="omega_n",
        numeric=2.0,
        unit="rad/s",
        display="omega_n = 2 rad/s",
    )

    assert item.output_key == "angular_frequency"
    assert _report("angular_frequency", item).passed


@pytest.mark.parametrize(
    "directions",
    [
        "omega=2rad/s cw방향이고 alpha=1rad/s^2 ccw방향",
        "omega=2rad/s clockwise and alpha=1rad/s^2 counter-clockwise",
    ],
)
def test_rigid_body_direction_forms_pass_verification_gate(directions: str):
    text = (
        "평면 강체에서 rBA=(1,0)m이다. "
        f"{directions}이다. B점 가속도를 구하라."
    )
    initial = solve_problem(text)
    assert initial.clarification is not None
    option = next(
        option
        for option in initial.clarification.options
        if option.patch.get("input_contract") == "rigid_aA_vector"
    )
    response = solve_problem(
        text,
        clarify_patch={
            **option.patch,
            "set_knowns": [
                {"symbol": "aAx", "value": 0.0, "unit": "m/s^2"},
                {"symbol": "aAy", "value": 0.0, "unit": "m/s^2"},
            ],
        },
    )

    assert response.ok is True, response.model_dump_json()
    assert response.verification.passed is True, response.model_dump_json()
    assert response.answer is not None
    assert response.answers


def test_legacy_local_study_migration_backfills_only_verified_engine_records(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")
    con = notebook._connect()
    valid_raw = {
        "ok": True,
        "verification": {"passed": True},
        "answers": [{"display": "v = 3 m/s"}],
    }
    invalid_raw = {
        "ok": True,
        "verification": {"passed": False},
    }
    con.executemany(
        """
        INSERT INTO records(
            problem_text, tags_json, raw_result_json, source, verified
        ) VALUES (?, '[]', ?, 'local-study', 1)
        """,
        [
            ("verified legacy", json.dumps(valid_raw)),
            ("unverified legacy", json.dumps(invalid_raw)),
            ("unknown legacy", None),
        ],
    )
    con.commit()
    con.close()

    by_problem = {
        record["problem_text"]: record
        for record in notebook.list_records()
    }

    assert by_problem["verified legacy"]["source"] == "engine"
    assert by_problem["verified legacy"]["verified"] is True
    assert by_problem["unverified legacy"]["source"] == "manual"
    assert by_problem["unverified legacy"]["verified"] is False
    assert by_problem["unknown legacy"]["source"] == "manual"
    assert by_problem["unknown legacy"]["verified"] is False


def test_adjacent_direction_clauses_bind_to_omega_and_alpha():
    parsed = _signs(
        "omega=2rad/s이며 반시계방향이고 "
        "alpha=3rad/s^2이며 시계방향"
    )

    assert parsed["omega_sign"] == 1.0
    assert parsed["alpha_sign"] == -1.0


def test_signed_initial_angular_velocity_passes_full_service_gate():
    text = (
        "고정축 회전에서 초기각속도 omega0=5rad/s이며 시계방향이고 "
        "각가속도 alpha=2rad/s^2이며 반시계방향이다. "
        "4s 후 최종 각속도를 구하라."
    )

    response = solve_problem(text)

    assert response.ok is True, response.model_dump_json()
    assert response.verification.passed is True, response.model_dump_json()
    angular_velocity = next(
        item
        for item in response.answers
        if item.output_key == "angular_velocity"
    )
    assert math.isclose(angular_velocity.numeric, 3.0)


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "omega=2rad/s, alpha=1rad/s^2 둘 다 반시계방향",
            1.0,
        ),
        (
            "omega=2rad/s and alpha=1rad/s^2 are both clockwise",
            -1.0,
        ),
    ],
)
def test_collective_direction_applies_to_both_named_quantities(
    text: str,
    expected: float,
):
    parsed = _signs(text)

    assert parsed["omega_sign"] == expected
    assert parsed["alpha_sign"] == expected


def test_collective_rigid_direction_passes_verification_gate():
    text = (
        "평면 강체에서 rBA=(1,0)m이다. "
        "omega=2rad/s, alpha=1rad/s^2 둘 다 반시계방향이다. "
        "B점 가속도를 구하라."
    )
    initial = solve_problem(text)
    option = next(
        option
        for option in initial.clarification.options
        if option.patch.get("input_contract") == "rigid_aA_vector"
    )
    response = solve_problem(
        text,
        clarify_patch={
            **option.patch,
            "set_knowns": [
                {"symbol": "aAx", "value": 0.0, "unit": "m/s^2"},
                {"symbol": "aAy", "value": 0.0, "unit": "m/s^2"},
            ],
        },
    )

    assert response.ok is True, response.model_dump_json()
    assert response.verification.passed is True, response.model_dump_json()


def test_legacy_local_study_api_input_backfills_verified_engine(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")
    raw = {
        "ok": True,
        "verification": {"passed": True},
        "answer": {"display": "v = 3.000 m/s"},
        "answers": [{"display": "v = 3.000 m/s"}],
    }

    record = records_route.create_record(
        RecordCreate(
            problem_text="cached verified result",
            answer_display="v = 3.000 m/s",
            raw_result=raw,
            source="local-study",
        )
    )

    assert record.source == "engine"
    assert record.verified is True


def test_legacy_local_study_api_input_fails_closed_to_manual(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")

    record = records_route.create_record(
        RecordCreate(
            problem_text="cached unverified result",
            raw_result={
                "ok": True,
                "verification": {"passed": False},
            },
            source="local-study",
        )
    )

    assert record.source == "manual"
    assert record.verified is False
