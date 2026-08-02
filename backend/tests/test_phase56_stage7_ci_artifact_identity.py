"""Stage 7 uploaded-artifact identity: the evidence must describe the source.

Background, because these controls only make sense against the defect they
close.  The gate used to record ``GITHUB_SHA`` in preference to the worktree.
On a ``pull_request`` event GitHub sets ``GITHUB_SHA`` to the ephemeral
``refs/pull/<n>/merge`` commit, so every pull_request-event Stage 7 run
uploaded a report naming a commit that is not the commit it checked out, not
reachable from any branch, and not resolvable by anyone auditing the run.  The
workflow was green throughout: nothing in it ever compared the head it checked
out with the head the report claimed.

The invariant these tests pin is

    configured expected head == git rev-parse HEAD == report exact_head_sha

together with the report's raw bytes still hashing to what the gate sealed when
it wrote them.  Each control asserts the *name* of the gate it hits, so a
refusal that happened to fire for an unrelated reason is not counted as the
property being checked.

Nothing here reads the authorised public archive; the whole file runs in
corpus-independent CI.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = (
    REPOSITORY_ROOT / "backend" / "tools" / "check_stage7_ci_artifact_identity.py"
)
GATE_PATH = (
    REPOSITORY_ROOT / "backend" / "tools" / "run_phase56_stage7_offline_gate.py"
)
WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github/workflows/phase56-stage7-offline-evaluation.yml"
)


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass(slots=True)` rebuilds its class and looks the module up in
    # `sys.modules`, so the entry has to exist before the body runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load(CHECKER_PATH, "stage7_artifact_identity_checker")


@pytest.fixture(scope="module")
def gate_module() -> Any:
    module = _load(GATE_PATH, "stage7_gate_for_identity_tests")
    try:
        yield module
    finally:
        sys.modules.pop("stage7_gate_for_identity_tests", None)


def _head_sha() -> str:
    return (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.strip()
        .casefold()
    )


def _report_document(head_sha: str) -> dict[str, Any]:
    """A minimal report with the shape the checker requires."""

    return {
        "schema": "dynatutor.phase56_stage7.offline_gate",
        "version": "1.0",
        "evaluator_version": "phase56-stage7-evaluator-v3",
        "contract_version": "1.0",
        "exact_head_sha": head_sha,
        "gates": [{"name": "structural", "result": "PASS", "detail": ""}],
        "public_corpus": {"supplied": False, "disposition": "NOT_RUN"},
        "lane_b": {"executed": False, "disposition": "NOT_RUN"},
        "external_model_calls": 0,
        "private_heldout_accesses": 0,
    }


def _write(path: Path, document: dict[str, Any]) -> tuple[Path, str]:
    """Write a report the way the gate does and return its raw digest."""

    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _check(report: Path, head: str, digest: str) -> dict[str, str]:
    return checker.check_artifact_identity(
        report_path=report,
        expected_head_sha=head,
        expected_raw_sha256=digest,
        repository_root=REPOSITORY_ROOT,
    )


def _refusal(report: Path, head: str, digest: str) -> str:
    with pytest.raises(checker.IdentityFailure) as excinfo:
        _check(report, head, digest)
    return excinfo.value.code


# ---------------------------------------------------------------------------
# The positive control, so the negatives below are known to be discriminating
# ---------------------------------------------------------------------------


def test_a_report_bound_to_the_checked_out_head_is_accepted(tmp_path: Path) -> None:
    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(head))
    identity = _check(report, head, digest)
    assert identity["expected_head_sha"] == head
    assert identity["checkout_head_sha"] == head
    assert identity["report_exact_head_sha"] == head
    assert identity["report_raw_sha256"] == digest


# ---------------------------------------------------------------------------
# 1-3.  Head disagreement, in each of the three directions it can occur
# ---------------------------------------------------------------------------


def test_a_stale_report_head_is_refused(tmp_path: Path) -> None:
    """The exact shape of the live defect: a real, older, wrong commit."""

    stale = "df27bc7dafd3a33abe7f8c49995296d17e22dfda"
    head = _head_sha()
    assert stale != head
    report, digest = _write(tmp_path / "report.json", _report_document(stale))
    assert (
        _refusal(report, head, digest)
        == "artifact_report_exact_head_sha_mismatch"
    )


def test_a_pull_request_merge_sha_in_the_report_is_refused(tmp_path: Path) -> None:
    """The precise value the defect wrote: refs/pull/N/merge, not the head."""

    merge_sha = "014732bea2e4b927c2a59a0194d01fe1b212187e"
    head = _head_sha()
    assert merge_sha != head
    report, digest = _write(tmp_path / "report.json", _report_document(merge_sha))
    assert (
        _refusal(report, head, digest)
        == "artifact_report_exact_head_sha_mismatch"
    )


def test_a_configured_head_that_is_not_the_checkout_is_refused(
    tmp_path: Path,
) -> None:
    configured = "0" * 39 + "1"
    report, digest = _write(tmp_path / "report.json", _report_document(configured))
    assert _refusal(report, configured, digest) == "checkout_head_sha_mismatch"


# ---------------------------------------------------------------------------
# 4-5.  The report changing after it was sealed
# ---------------------------------------------------------------------------


def test_one_mutated_byte_after_the_seal_is_refused(tmp_path: Path) -> None:
    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(head))
    raw = report.read_bytes()
    report.write_bytes(raw[:-1] + b" \n")
    assert _refusal(report, head, digest) == "artifact_report_raw_digest_mismatch"


def test_substitution_by_another_valid_report_is_refused(tmp_path: Path) -> None:
    """A swap that parses, validates and names the right head still fails."""

    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(head))
    replacement = _report_document(head)
    replacement["gates"] = [{"name": "structural", "result": "PASS", "detail": "x"}]
    report.write_text(
        json.dumps(replacement, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    # It would pass every semantic gate; only the seal distinguishes it.
    assert _refusal(report, head, digest) == "artifact_report_raw_digest_mismatch"


def test_a_synthetic_fixture_at_the_upload_path_is_refused(tmp_path: Path) -> None:
    """A test fixture dropped where the upload reads must not be publishable."""

    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(head))
    synthetic = _report_document(head)
    synthetic["public_corpus"] = {"supplied": False, "disposition": "NOT_RUN"}
    synthetic["lane_b"] = {"executed": True, "disposition": "PASS", "result": "PASS"}
    report.write_text(
        json.dumps(synthetic, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    assert _refusal(report, head, digest) == "artifact_report_raw_digest_mismatch"


# ---------------------------------------------------------------------------
# 6-7.  Path isolation
# ---------------------------------------------------------------------------


def test_a_later_writer_elsewhere_leaves_the_sealed_report_untouched(
    tmp_path: Path,
) -> None:
    """A second report writer must not be able to reach the upload path.

    The gate has no default output path to fall back on, so a command that does
    not name one cannot land on another command's file.  Here the second writer
    names its own path and the first report stays valid.
    """

    head = _head_sha()
    upload, digest = _write(tmp_path / "upload.json", _report_document(head))
    other = _report_document(head)
    other["gates"] = [{"name": "other", "result": "PASS", "detail": ""}]
    _write(tmp_path / "somewhere-else.json", other)
    assert _check(upload, head, digest)["report_raw_sha256"] == digest


def test_two_concurrent_writers_do_not_collide(tmp_path: Path) -> None:
    head = _head_sha()
    first, first_digest = _write(tmp_path / "run-1.json", _report_document(head))
    second_doc = _report_document(head)
    second_doc["gates"] = [{"name": "second", "result": "PASS", "detail": ""}]
    second, second_digest = _write(tmp_path / "run-2.json", second_doc)
    assert first != second
    assert first_digest != second_digest
    assert _check(first, head, first_digest)["report_raw_sha256"] == first_digest
    assert _check(second, head, second_digest)["report_raw_sha256"] == second_digest


def test_the_gate_refuses_to_run_without_an_explicit_output_path() -> None:
    """No default output path exists, so nothing can collide on one."""

    source = GATE_PATH.read_text(encoding="utf-8")
    assert 'default=REPOSITORY_ROOT / "stage7_offline_gate_report.json"' not in source
    completed = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        cwd=REPOSITORY_ROOT / "backend",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode != 0
    assert "--output" in completed.stderr


# ---------------------------------------------------------------------------
# 8.  Provenance: the head comes from the source, not from a constant
# ---------------------------------------------------------------------------


def test_the_recorded_head_comes_from_the_worktree_not_the_environment(
    gate_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression control for the live defect.

    ``GITHUB_SHA`` is set to the pull_request merge commit, exactly as GitHub
    sets it.  The resolved head must ignore it and stay the checked-out head.
    """

    monkeypatch.setenv("GITHUB_SHA", "014732bea2e4b927c2a59a0194d01fe1b212187e")
    assert gate_module._checkout_head_sha() == _head_sha()
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    assert gate_module._checkout_head_sha() == _head_sha()


def test_the_gate_never_reads_github_sha() -> None:
    """Structural, so the preference cannot be reintroduced anywhere in the file."""

    source = GATE_PATH.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    # The docstring names GITHUB_SHA to explain why it is not read; what must
    # not exist is a lookup of it.
    assert 'environ.get("GITHUB_SHA"' not in code
    assert 'environ["GITHUB_SHA"]' not in code


def test_no_hard_coded_checkpoint_sha_is_baked_into_the_gate_or_checker() -> None:
    """A 40-hex literal in either tool could become a stale recorded head."""

    for path in (GATE_PATH, CHECKER_PATH):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\b[0-9a-f]{40}\b", source):
            pytest.fail(f"{path.name} carries a hard-coded commit: {match.group(0)}")


# ---------------------------------------------------------------------------
# 9-12.  The checker fails closed on malformed input
# ---------------------------------------------------------------------------


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_bytes(b"{not json")
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    assert _refusal(report, _head_sha(), digest) == "artifact_report_malformed_json"


def test_a_json_document_that_is_not_an_object_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_bytes(b"[1, 2, 3]")
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    assert _refusal(report, _head_sha(), digest) == "artifact_report_not_an_object"


def test_a_missing_report_fails_closed(tmp_path: Path) -> None:
    head = _head_sha()
    assert (
        _refusal(tmp_path / "absent.json", head, "0" * 64)
        == "artifact_report_missing"
    )


def test_a_missing_exact_head_sha_fails_closed(tmp_path: Path) -> None:
    head = _head_sha()
    document = _report_document(head)
    del document["exact_head_sha"]
    report, digest = _write(tmp_path / "report.json", document)
    # The schema gate names the absent field before the head gate is reached.
    assert _refusal(report, head, digest) == "artifact_report_schema_incomplete"


def test_a_null_exact_head_sha_fails_closed(tmp_path: Path) -> None:
    head = _head_sha()
    document = _report_document(head)
    document["exact_head_sha"] = None
    report, digest = _write(tmp_path / "report.json", document)
    assert (
        _refusal(report, head, digest)
        == "artifact_report_exact_head_sha_malformed"
    )


@pytest.mark.parametrize(
    "spelling",
    (
        "D709C8514314A82770657DF46A9D49B62151AAEF",
        "d709c851",
        " d709c8514314a82770657df46a9d49b62151aaef",
        "d709c8514314a82770657df46a9d49b62151aaef ",
        "d709c8514314a82770657df46a9d49b62151aaef\n",
        "d709c8514314a82770657df46a9d49b62151aaefaa",
        "g709c8514314a82770657df46a9d49b62151aaef0",
    ),
)
def test_a_non_canonical_sha_spelling_is_refused(
    tmp_path: Path, spelling: str
) -> None:
    """Uppercase, abbreviated, padded and over-long spellings are all refused."""

    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(spelling))
    assert (
        _refusal(report, head, digest)
        == "artifact_report_exact_head_sha_malformed"
    )


def test_the_seal_is_over_raw_bytes_not_newline_normalised_text(
    tmp_path: Path,
) -> None:
    """CRLF and LF must not collapse to one digest.

    A text-mode read normalises line endings, so two files that differ only in
    their line endings would seal identically and a substitution between them
    would be invisible.
    """

    head = _head_sha()
    body = json.dumps(_report_document(head), sort_keys=True, indent=2) + "\n"
    lf = tmp_path / "lf.json"
    lf.write_bytes(body.encode("utf-8"))
    crlf = tmp_path / "crlf.json"
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))

    lf_digest = hashlib.sha256(lf.read_bytes()).hexdigest()
    crlf_digest = hashlib.sha256(crlf.read_bytes()).hexdigest()
    assert lf_digest != crlf_digest
    assert lf.read_text() == crlf.read_text()  # text mode cannot tell them apart

    assert _check(lf, head, lf_digest)["report_raw_sha256"] == lf_digest
    assert _refusal(crlf, head, lf_digest) == "artifact_report_raw_digest_mismatch"


def test_a_malformed_expected_digest_fails_closed(tmp_path: Path) -> None:
    head = _head_sha()
    report, _ = _write(tmp_path / "report.json", _report_document(head))
    for bad in ("", "not-a-digest", "0" * 63, "0" * 65, "A" * 64):
        with pytest.raises(checker.IdentityFailure) as excinfo:
            _check(report, head, bad)
        assert excinfo.value.code == "artifact_expected_raw_sha256_malformed", bad


def test_a_malformed_expected_head_fails_closed(tmp_path: Path) -> None:
    head = _head_sha()
    report, digest = _write(tmp_path / "report.json", _report_document(head))
    for bad in ("", "1234", "z" * 40, head.upper() + "0"):
        with pytest.raises(checker.IdentityFailure) as excinfo:
            _check(report, bad, digest)
        assert excinfo.value.code == "expected_head_sha_malformed", bad


# ---------------------------------------------------------------------------
# Semantic contract: schema, privacy, and the corpus-independent scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ("schema", "version", "gates", "public_corpus"))
def test_a_missing_required_field_fails_closed(tmp_path: Path, field: str) -> None:
    head = _head_sha()
    document = _report_document(head)
    del document[field]
    report, digest = _write(tmp_path / "report.json", document)
    assert _refusal(report, head, digest) == "artifact_report_schema_incomplete"


def test_an_unexpected_schema_is_refused(tmp_path: Path) -> None:
    head = _head_sha()
    document = _report_document(head)
    document["schema"] = "dynatutor.something_else"
    report, digest = _write(tmp_path / "report.json", document)
    assert _refusal(report, head, digest) == "artifact_report_schema_unexpected"


def test_a_corpus_independent_run_claiming_a_public_lane_pass_is_refused(
    tmp_path: Path,
) -> None:
    """NOT_RUN is not PASS, and a report must not be able to say otherwise."""

    head = _head_sha()
    for lane in ("lane_b", "lane_c", "compositional_12", "hard_safety"):
        document = _report_document(head)
        document["public_corpus"] = {"supplied": False, "disposition": "NOT_RUN"}
        document[lane] = {"result": "PASS"}
        report, digest = _write(tmp_path / f"{lane}.json", document)
        assert (
            _refusal(report, head, digest)
            == "artifact_report_corpus_independent_claims_public_pass"
        ), lane


def test_a_supplied_corpus_run_may_report_public_lane_passes(tmp_path: Path) -> None:
    """The scope gate must not fire when the archive really was supplied."""

    head = _head_sha()
    document = _report_document(head)
    document["public_corpus"] = {"supplied": True, "disposition": "PASS"}
    document["lane_b"] = {"executed": True, "disposition": "PASS", "result": "PASS"}
    report, digest = _write(tmp_path / "report.json", document)
    assert _check(report, head, digest)["report_exact_head_sha"] == head


def test_a_leaked_sensitive_field_is_refused(tmp_path: Path) -> None:
    head = _head_sha()
    document = _report_document(head)
    document["problem_text"] = "a case body that must never leave the runner"
    report, digest = _write(tmp_path / "report.json", document)
    assert _refusal(report, head, digest) == "artifact_report_privacy_unsafe"


def test_a_nonzero_external_call_count_is_refused(tmp_path: Path) -> None:
    head = _head_sha()
    document = _report_document(head)
    document["external_model_calls"] = 1
    report, digest = _write(tmp_path / "report.json", document)
    assert (
        _refusal(report, head, digest) == "artifact_report_offline_claim_violated"
    )


def test_the_checker_parses_rather_than_greps(tmp_path: Path) -> None:
    """The right SHA somewhere in the file is not the right SHA in the field."""

    head = _head_sha()
    document = _report_document("0" * 40)
    # The correct head is present in the document, just not where it counts.
    document["gates"] = [{"name": head, "result": "PASS", "detail": head}]
    report, digest = _write(tmp_path / "report.json", document)
    assert head in report.read_text(encoding="utf-8")
    assert (
        _refusal(report, head, digest)
        == "artifact_report_exact_head_sha_mismatch"
    )


# ---------------------------------------------------------------------------
# 13-15.  The workflow itself
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_the_workflow_writes_the_report_to_a_run_unique_path(
    workflow_text: str,
) -> None:
    assert (
        'path="${RUNNER_TEMP}/stage7-offline-${EXACT_HEAD_SHA}-'
        '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.json"' in workflow_text
    )
    assert 'echo "STAGE7_REPORT_PATH=${path}" >> "$GITHUB_ENV"' in workflow_text
    # Refuse to reuse a path that already exists, so a collision is a failure
    # rather than a silent overwrite.
    assert 'test ! -e "$path"' in workflow_text


def test_the_workflow_binds_the_gate_to_the_configured_head(
    workflow_text: str,
) -> None:
    assert '--expect-head-sha "$EXACT_HEAD_SHA"' in workflow_text
    assert '--output "$STAGE7_REPORT_PATH"' in workflow_text


def test_the_workflow_runs_the_identity_checker_immediately_before_upload(
    workflow_text: str,
) -> None:
    checker_index = workflow_text.index("check_stage7_ci_artifact_identity.py")
    upload_index = workflow_text.index("Upload redacted aggregate artifact")
    assert checker_index < upload_index
    between = workflow_text[checker_index:upload_index]
    # Nothing between validation and upload may write a report.
    for writer in ("run_phase56_stage7_offline_gate.py", "pytest", "> \"$STAGE7"):
        assert writer not in between


def test_the_upload_is_conditioned_on_the_identity_check(workflow_text: str) -> None:
    upload = workflow_text[
        workflow_text.index("Upload redacted aggregate artifact") :
    ]
    assert (
        "if: always() && steps.stage7_artifact_identity.outcome == 'success'"
        in upload
    )
    assert "path: ${{ env.STAGE7_REPORT_PATH }}" in upload


def test_the_upload_path_is_the_validated_path(workflow_text: str) -> None:
    """One variable names the written, validated and published file."""

    assert workflow_text.count("STAGE7_REPORT_PATH") >= 4
    assert "stage7_offline_gate_report.json" not in workflow_text


def test_the_checker_receives_the_seal_the_gate_produced(workflow_text: str) -> None:
    assert (
        "sed -n 's/^STAGE7_OFFLINE_GATE_REPORT_SHA256=//p'" in workflow_text
    )
    assert '--expect-raw-sha256 "$STAGE7_REPORT_RAW_SHA256"' in workflow_text


def test_no_test_resolves_the_upload_path_or_writes_into_runner_temp() -> None:
    """No test can reach the file the workflow is going to publish.

    The upload path exists only at run time, in ``RUNNER_TEMP``, under a name
    carrying the head, the run id and the attempt.  A test could only land on
    it by reading ``STAGE7_REPORT_PATH`` out of the environment or by writing
    into ``RUNNER_TEMP`` itself, so those are the two things forbidden here.
    Mentioning the variable name while asserting *about the workflow text* is
    not reaching the path, and is not what this forbids.
    """

    # Composed rather than written out, so this file does not match its own
    # scan and no file has to be excluded from it.
    resolvers = tuple(
        template.format(name=name)
        for name in ("STAGE7_REPORT_PATH", "RUNNER_TEMP")
        for template in ('environ.get("{name}"', 'environ["{name}"]', 'getenv("{name}"')
    )
    offenders: list[str] = []
    for path in (REPOSITORY_ROOT / "backend" / "tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(resolver in text for resolver in resolvers):
            offenders.append(str(path.relative_to(REPOSITORY_ROOT)))
    assert offenders == []


def test_every_in_suite_gate_invocation_writes_into_its_own_tmp_dir() -> None:
    """A test that runs the gate must name a private output path.

    The gate has no default output, so an invocation that names nothing fails;
    this pins the stronger property that the paths tests do name are private
    per-test paths rather than a shared file two tests could interleave on.
    """

    pattern = re.compile(r'"--output",\s*\n\s*str\((?P<expr>[^)]*)\)')
    invocations = 0
    for path in (REPOSITORY_ROOT / "backend" / "tests").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "run_phase56_stage7_offline_gate" not in text:
            continue
        for match in pattern.finditer(text):
            invocations += 1
            expr = match.group("expr")
            assert "tmp" in expr.casefold(), f"{path.name}: {expr}"
    assert invocations >= 1
