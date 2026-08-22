"""The dependency lock, as a contract a strict report can be attributed to.

Every test here is a pure function over supplied data.  None builds a virtual
environment, installs a package, or reaches a network — the point of the module
under test is that the environment contract is checkable without one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.phase56_stage7.locked_environment import (
    ENVIRONMENT_WITNESS_DISTRIBUTIONS,
    LOCKED_ENVIRONMENT_CONTRACT_VERSION,
    OFFLINE_REQUIRED_EMPTY_VARIABLES,
    LockedRequirementParseError,
    build_locked_environment_record,
    canonical_distribution_name,
    compare_locked_versions,
    offline_environment,
    offline_environment_is_clean,
    parse_locked_requirements,
)
from tools.run_phase56_stage7_locked_strict import _venv_python_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = REPOSITORY_ROOT / "backend" / "requirements-lock.txt"


def _lock_text() -> str:
    return LOCK_FILE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Parsing the lock
# --------------------------------------------------------------------------


def test_the_repository_lock_file_parses_into_exact_pins() -> None:
    requirements = parse_locked_requirements(_lock_text())

    assert requirements, "the repository lock file pins nothing"
    assert all(requirement.version for requirement in requirements)
    names = [requirement.canonical_name for requirement in requirements]
    assert len(names) == len(set(names)), "the lock file pins a name twice"


def test_the_lock_file_pins_every_distribution_lane_d_depends_on() -> None:
    pinned = {
        requirement.canonical_name
        for requirement in parse_locked_requirements(_lock_text())
    }

    # `starlette` and `pydantic-core` are transitive and deliberately not
    # pinned directly; the rest are what Lane D and the strict gate execute.
    for name in ("fastapi", "pydantic", "pytest", "httpx", "sympy"):
        assert name in pinned


def test_comments_and_blank_lines_are_skipped() -> None:
    text = "# a comment\n\nfastapi==0.128.2\n\n  # indented comment\npytest==9.0.2\n"

    requirements = parse_locked_requirements(text)

    assert [item.canonical_name for item in requirements] == ["fastapi", "pytest"]


def test_an_extras_marker_is_parsed_and_normalised() -> None:
    (requirement,) = parse_locked_requirements("uvicorn[standard]==0.48.0\n")

    assert requirement.canonical_name == "uvicorn"
    assert requirement.version == "0.48.0"
    assert requirement.extras == ("standard",)


def test_a_trailing_comment_on_a_pin_is_stripped() -> None:
    (requirement,) = parse_locked_requirements("pytest==9.0.2  # the runner\n")

    assert requirement.version == "9.0.2"


@pytest.mark.parametrize(
    "line",
    [
        "fastapi>=0.128.2",
        "fastapi",
        "fastapi<1.0",
        "fastapi==0.128.2 ; python_version < '3.12'",
        "-r other-requirements.txt",
        "git+https://example.invalid/pkg.git",
    ],
)
def test_a_requirement_that_does_not_pin_exactly_fails_closed(line: str) -> None:
    with pytest.raises(LockedRequirementParseError):
        parse_locked_requirements(line + "\n")


def test_a_duplicate_pin_fails_closed_rather_than_last_one_winning() -> None:
    with pytest.raises(LockedRequirementParseError):
        parse_locked_requirements("fastapi==0.128.2\nfastapi==0.127.0\n")


def test_a_duplicate_pin_is_caught_across_spellings_of_one_name() -> None:
    with pytest.raises(LockedRequirementParseError):
        parse_locked_requirements("Pillow==11.3.0\npillow==11.2.0\n")


def test_an_empty_lock_file_fails_closed() -> None:
    with pytest.raises(LockedRequirementParseError):
        parse_locked_requirements("# nothing but a comment\n")


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("Pillow", "pillow"),
        ("pydantic_core", "pydantic-core"),
        ("pydantic.core", "pydantic-core"),
        ("PYDANTIC--CORE", "pydantic-core"),
    ],
)
def test_distribution_names_canonicalise_per_pep_503(
    written: str, canonical: str
) -> None:
    assert canonical_distribution_name(written) == canonical


# --------------------------------------------------------------------------
# Comparing the lock against a resolved environment
# --------------------------------------------------------------------------


def test_an_exactly_matching_environment_reports_no_mismatch() -> None:
    required = parse_locked_requirements("fastapi==0.128.2\npytest==9.0.2\n")

    mismatches = compare_locked_versions(
        required=required, resolved={"fastapi": "0.128.2", "pytest": "9.0.2"}
    )

    assert mismatches == ()


def test_a_wrong_version_is_reported_with_both_versions() -> None:
    required = parse_locked_requirements("fastapi==0.128.2\n")

    (mismatch,) = compare_locked_versions(
        required=required, resolved={"fastapi": "0.127.0"}
    )

    assert mismatch.canonical_name == "fastapi"
    assert mismatch.required_version == "0.128.2"
    assert mismatch.resolved_version == "0.127.0"
    assert mismatch.missing is False


def test_a_distribution_that_is_absent_is_distinguished_from_a_wrong_version() -> None:
    required = parse_locked_requirements("fastapi==0.128.2\n")

    (mismatch,) = compare_locked_versions(required=required, resolved={})

    assert mismatch.missing is True
    assert mismatch.resolved_version is None


def test_a_resolution_spelled_differently_still_matches_its_pin() -> None:
    required = parse_locked_requirements("Pillow==11.3.0\n")

    assert (
        compare_locked_versions(required=required, resolved={"pillow": "11.3.0"}) == ()
    )


def test_extra_resolved_distributions_are_not_mismatches() -> None:
    required = parse_locked_requirements("fastapi==0.128.2\n")

    mismatches = compare_locked_versions(
        required=required,
        resolved={"fastapi": "0.128.2", "starlette": "0.50.0", "anyio": "4.14.2"},
    )

    assert mismatches == ()


# --------------------------------------------------------------------------
# The offline environment
# --------------------------------------------------------------------------


def test_every_variable_the_gate_requires_empty_is_named() -> None:
    from evaluation.phase56_stage7 import network_guard

    source = Path(network_guard.__file__).read_text(encoding="utf-8")
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "MECHANICS_MODELER_BASE_URL",
        "MECHANICS_FIGURE_BASE_URL",
    ):
        assert name in source
        assert name in OFFLINE_REQUIRED_EMPTY_VARIABLES


def test_a_credential_bearing_environment_is_scrubbed() -> None:
    base = {
        "PATH": "/usr/bin",
        "HOME": "/root",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "OPENAI_API_KEY": "sk-not-a-real-key",
    }

    scrubbed = offline_environment(base)

    assert offline_environment_is_clean(scrubbed)
    assert "ANTHROPIC_BASE_URL" not in scrubbed
    assert "OPENAI_API_KEY" not in scrubbed


def test_scrubbing_removes_rather_than_blanks_so_nothing_reads_it_back() -> None:
    scrubbed = offline_environment({"OPENAI_API_KEY": "sk-not-a-real-key"})

    assert scrubbed == {}


def test_scrubbing_carries_every_other_variable_through_untouched() -> None:
    base = {
        "PATH": "/usr/bin",
        "STAGE7_PUBLIC_CORPUS_PATH": "/root/elsewhere/corpus.zip",
        "ANTHROPIC_API_KEY": "value",
    }

    scrubbed = offline_environment(base)

    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["STAGE7_PUBLIC_CORPUS_PATH"] == "/root/elsewhere/corpus.zip"


def test_a_dirty_environment_is_detected_before_a_run_starts() -> None:
    assert not offline_environment_is_clean({"ANTHROPIC_BASE_URL": "https://x.invalid"})
    assert offline_environment_is_clean({"ANTHROPIC_BASE_URL": ""})
    assert offline_environment_is_clean({})


# --------------------------------------------------------------------------
# The environment record
# --------------------------------------------------------------------------


def test_a_matching_record_reports_locked_and_carries_the_witnesses() -> None:
    record = build_locked_environment_record(
        python_version="3.11.15",
        lock_file="backend/requirements-lock.txt",
        lock_text="fastapi==0.128.2\npytest==9.0.2\n",
        resolved={
            "fastapi": "0.128.2",
            "pytest": "9.0.2",
            "starlette": "0.50.0",
        },
    )

    assert record.locked is True
    assert record.version == LOCKED_ENVIRONMENT_CONTRACT_VERSION
    assert record.python_version == "3.11.15"
    witnesses = {item.canonical_name: item.version for item in record.witness_versions}
    assert witnesses["starlette"] == "0.50.0"
    assert witnesses["fastapi"] == "0.128.2"


def test_a_record_with_a_mismatch_is_not_locked() -> None:
    record = build_locked_environment_record(
        python_version="3.11.15",
        lock_file="backend/requirements-lock.txt",
        lock_text="fastapi==0.128.2\n",
        resolved={"fastapi": "0.127.0"},
    )

    assert record.locked is False
    assert record.mismatches[0].resolved_version == "0.127.0"


def test_an_absent_witness_is_omitted_rather_than_recorded_as_a_mismatch() -> None:
    record = build_locked_environment_record(
        python_version="3.11.15",
        lock_file="backend/requirements-lock.txt",
        lock_text="fastapi==0.128.2\n",
        resolved={"fastapi": "0.128.2"},
    )

    assert record.locked is True
    assert all(item.version for item in record.witness_versions)
    assert "scipy" not in {item.canonical_name for item in record.witness_versions}


def test_the_record_is_json_stable_and_carries_no_case_material() -> None:
    record = build_locked_environment_record(
        python_version="3.11.15",
        lock_file="backend/requirements-lock.txt",
        lock_text=_lock_text(),
        resolved={
            requirement.canonical_name: requirement.version
            for requirement in parse_locked_requirements(_lock_text())
        },
    )

    payload = record.model_dump(mode="json")
    text = repr(payload)

    assert record.locked is True
    for forbidden in ("case_id", "problem_text", "expected_answer", "gold"):
        assert forbidden not in text
    assert "sk-" not in text


def test_the_record_rejects_an_unknown_field() -> None:
    from evaluation.phase56_stage7.locked_environment import LockedEnvironmentRecordV1

    with pytest.raises(ValidationError):
        LockedEnvironmentRecordV1(
            python_version="3.11.15",
            lock_file="backend/requirements-lock.txt",
            unexpected="value",
        )


def test_the_witness_list_names_the_framework_lane_d_asserts_against() -> None:
    # Lane D's failure was a route-registration behaviour that lives in
    # starlette, one layer below the pinned fastapi.  A witness list that
    # omitted it would leave that failure unattributable again.
    assert "starlette" in ENVIRONMENT_WITNESS_DISTRIBUTIONS
    assert "fastapi" in ENVIRONMENT_WITNESS_DISTRIBUTIONS


def test_the_locked_strict_runner_names_the_test_that_motivated_it() -> None:
    runner = REPOSITORY_ROOT / "backend" / "tools" / "run_phase56_stage7_locked_strict.py"
    source = runner.read_text(encoding="utf-8")

    assert "test_openapi_registers_stage6_routes_exactly_once" in source
    # Lane D is run isolated *and* whole; one without the other cannot separate
    # "this test is order-dependent" from "this environment is wrong".
    assert "LANE_D_ISOLATED_TEST" in source
    assert "LANE_D_SUITES" in source


def test_the_locked_strict_runner_uses_the_native_virtualenv_interpreter() -> None:
    root = Path("locked-environment")

    assert _venv_python_path(root, platform_name="posix") == root / "bin" / "python"
    assert _venv_python_path(root, platform_name="nt") == (
        root / "Scripts" / "python.exe"
    )
