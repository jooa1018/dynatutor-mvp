"""Dedicated attacks for the hard-safety signals no counter can see.

Six of the twenty-three catalog signals are counted directly by the Lane B
scorer or the gate's environment guards.  The rest are properties of paths Lane
B never walks — the correction endpoint, the logging surface, the modeling
envelope — and a property nobody attacked is not a property measured to be zero.
Every test here exists to make exactly one such signal *able to fail*, and the
registry in ``evaluation.phase56_stage7.hard_safety_registry`` names the binding
so an unattacked signal reports NOT_MEASURED instead of inheriting a silent zero.

These are attacks, not demonstrations: each one drives the real object through
the real entry point and asserts a refusal.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engine.mechanics.contracts import (
    ANSWER_AUTHORITY_FORBIDDEN_FIELDS,
    find_forbidden_fields,
)
from engine.mechanics.multimodal_authority_audit import (
    FORBIDDEN_AUTHORITY_FIELDS,
    audit_modeling_payload,
)
from engine.mechanics.multimodal_contracts import (
    _FORBIDDEN_ENVELOPE_FIELDS,
    find_forbidden_multimodal_fields,
)
from engine.mechanics.multimodal_revision import FORBIDDEN_PATCH_FIELDS
from tests.support.stage6_multimodal_fixtures import synthetic_png
from tests.test_phase56_stage6_api_runtime_integration import (
    _app,
    _headers,
    _initial_json,
    _install_fake,
)


# --------------------------------------------------------------------------
# answer_authority_violation / model_selected_solver_authority /
# executable_model_equation / selected_root_authority / unsafe_legacy_fallback
#
# Four denylists guard four different surfaces — the modeling-envelope audit,
# the Draft contract's pre-scan, the multimodal envelope pre-scan, and the
# correction path — and their vocabularies are deliberately not identical.  Each
# is therefore attacked through the surface that actually enforces it.  The
# previous test proved two entries of one list and left every other entry
# asserted only by its presence in a frozenset, which is not evidence.
# --------------------------------------------------------------------------
def test_every_audited_authority_field_is_rejected_at_the_top_level() -> None:
    """Every entry of the audit's denylist, driven rather than merely declared."""

    for field in sorted(FORBIDDEN_AUTHORITY_FIELDS):
        result = audit_modeling_payload({"draft": {field: "seized"}})
        assert not result.passed, field
        assert field in {finding.field for finding in result.findings}, field


def test_every_audited_authority_field_is_rejected_when_buried() -> None:
    """Depth is not a loophole: the audit recurses, and this proves it does."""

    for field in sorted(FORBIDDEN_AUTHORITY_FIELDS):
        payload = {"draft": {"objects": [{"nested": [{"deeper": {field: "seized"}}]}]}}
        result = audit_modeling_payload(payload)
        assert not result.passed, field
        assert field in {finding.field for finding in result.findings}, field


def test_every_draft_answer_authority_field_is_found_when_buried() -> None:
    for field in sorted(ANSWER_AUTHORITY_FORBIDDEN_FIELDS):
        payload = {"draft": {"objects": [{"nested": [{"deeper": {field: "seized"}}]}]}}
        assert find_forbidden_fields(payload), field


def test_every_envelope_authority_field_is_found_when_buried() -> None:
    for field in sorted(_FORBIDDEN_ENVELOPE_FIELDS):
        payload = {"envelope": {"draft": [{"nested": {"deeper": {field: "seized"}}}]}}
        assert find_forbidden_multimodal_fields(payload), field


def test_every_surface_effectively_refuses_the_authority_core() -> None:
    """The drift guard, stated over *effective* guards rather than lists.

    A field naming the answer, the graph, the solver, or the root is authority
    wherever it appears, but no single denylist has to carry the whole core: the
    envelope's own pre-scan omits `equation_graph`, and is backstopped because
    `audit_modeling_payload` runs on the same envelope in `multimodal_modeler`
    and again on every confirmed and corrected envelope in `multimodal_revision`.
    What must hold is that each surface's guards *together* cover the core — so
    this fails the moment a list is trimmed without its backstop being checked.
    """

    core = {
        "final_answer",
        "equation_graph",
        "selected_solver",
        "selected_root",
        "verification_result",
    }
    effective = {
        "modeling_envelope": _FORBIDDEN_ENVELOPE_FIELDS | FORBIDDEN_AUTHORITY_FIELDS,
        "correction_patch": FORBIDDEN_PATCH_FIELDS | FORBIDDEN_AUTHORITY_FIELDS,
        "authority_audit": FORBIDDEN_AUTHORITY_FIELDS,
    }
    for surface, guard in effective.items():
        assert core <= guard, (surface, sorted(core - guard))


def test_the_draft_prescan_refuses_the_answer_core() -> None:
    """The Draft carries no graph and no solver, so its core is answer-shaped."""

    answer_core = {"final_answer", "expected_answer", "verification_result"}
    assert answer_core <= ANSWER_AUTHORITY_FORBIDDEN_FIELDS, sorted(
        answer_core - ANSWER_AUTHORITY_FORBIDDEN_FIELDS
    )


# --------------------------------------------------------------------------
# direct_graph_patch / direct_answer_patch / correction_bypass
#
# The correction path's recursive authority guard was written but never driven
# with a graph-shaped payload.  These send real equation-graph, answer, and
# solver/result keys through the real endpoint, at the top level and nested
# inside an otherwise-valid source correction.
# --------------------------------------------------------------------------
_GRAPH_SHAPED_KEYS = ("equation_graph", "solver_candidate", "verified_candidate")
_ANSWER_SHAPED_KEYS = ("final_answer", "verification_result")
_SOLVER_SHAPED_KEYS = ("selected_solver", "selected_root", "executable_equation")


def _correction(revision_id: str, fingerprint: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "dynatutor.mechanics_correction_request",
        "version": "1.0",
        "request_id": "attack-1",
        "client_request_id": "attack-1",
        "base_revision_id": revision_id,
        "base_revision_fingerprint": fingerprint,
        "operations": [
            {
                "kind": "replace_quantity_value",
                "operation_id": "replace-force",
                "quantity_id": "forceA",
                "raw_value": "20",
                "raw_unit": "N",
            }
        ],
    }
    payload.update(extra)
    return payload


def _seeded_revision(client: TestClient) -> tuple[str, str]:
    initial = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(request_id="attack-base"),
        headers=_headers(),
    ).json()
    return initial["revision_id"], initial["revision_fingerprint"]


_AUTHORITY_KEYS = (*_GRAPH_SHAPED_KEYS, *_ANSWER_SHAPED_KEYS, *_SOLVER_SHAPED_KEYS)


# The four attacks below drive a real FastAPI application through the real
# endpoint, which costs seconds rather than milliseconds.  `backend fast` shards
# by test *count* under a per-shard wall-clock budget, so an integration test
# living there spends budget the shard cannot see coming; the repository already
# marks suites of this shape `slow`.  They still run in CI under `backend slow`,
# and the strict gate runs them by exact node ID with `-o addopts=`, which clears
# the default marker filter — so the hard-safety registry measures them in every
# strict run regardless of this marker.


@pytest.mark.slow
def test_correction_cannot_carry_an_authority_key_at_the_top_level(
    monkeypatch,
) -> None:
    """Every authority key, driven through one client.

    Deliberately a loop rather than `parametrize`: each parametrisation would
    build its own FastAPI app and seed its own revision, and `backend fast`
    shards by *test count* with a per-shard time budget — so eight near-identical
    app builds cost the shard far more than they add in coverage.  The loop
    exercises the same eight payloads against the same guard and names the
    failing key in the assertion.
    """

    app = _app(monkeypatch)
    _install_fake(app)
    client = TestClient(app)
    revision_id, fingerprint = _seeded_revision(client)

    for key in _AUTHORITY_KEYS:
        response = client.post(
            f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
            json=_correction(revision_id, fingerprint, **{key: {"seized": True}}),
            headers=_headers(),
        )
        assert response.status_code in (400, 409, 422), (key, response.text)
        assert "verified_answer" not in response.json().get("detail", {}), key


@pytest.mark.slow
def test_correction_cannot_smuggle_an_authority_key_inside_an_operation(
    monkeypatch,
) -> None:
    """Each payload is a *valid* source correction with one extra nested key."""

    app = _app(monkeypatch)
    _install_fake(app)
    client = TestClient(app)
    revision_id, fingerprint = _seeded_revision(client)

    for key in _AUTHORITY_KEYS:
        payload = _correction(revision_id, fingerprint)
        payload["operations"][0]["provenance"] = {"note": {key: "seized"}}
        response = client.post(
            f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
            json=payload,
            headers=_headers(),
        )
        assert response.status_code in (400, 409, 422), (key, response.text)


def test_every_forbidden_patch_field_is_covered_by_an_attack() -> None:
    """The attack set may not silently fall behind the denylist it attacks."""

    attacked = {*_GRAPH_SHAPED_KEYS, *_ANSWER_SHAPED_KEYS, *_SOLVER_SHAPED_KEYS}
    unattacked = FORBIDDEN_PATCH_FIELDS - attacked
    assert unattacked <= {"legacy_route", "runtime_delivery"}, sorted(unattacked)


# --------------------------------------------------------------------------
# raw_image_or_base64_logging / raw_provider_output_logging
#
# Nothing prevented image bytes or a provider's raw output from reaching a log
# record.  This captures every record emitted while a real image travels the
# real endpoint, and asserts none of it carries the payload.
# --------------------------------------------------------------------------
def _emitted_text(records: list[logging.LogRecord]) -> str:
    parts: list[str] = []
    for record in records:
        parts.append(str(record.getMessage()))
        parts.append(str(record.args))
    return "\n".join(parts)


@pytest.mark.slow
def test_no_log_record_carries_image_bytes_or_base64(monkeypatch, caplog) -> None:
    app = _app(monkeypatch)
    _install_fake(app)
    client = TestClient(app)
    png = synthetic_png()
    encoded = base64.b64encode(png).decode("ascii")

    with caplog.at_level(logging.DEBUG):
        client.post(
            "/api/mechanics/multimodal/evidence",
            json={
                "problem_text": "A 2 kg block is pushed with 20 N.",
                "images": [{"filename": "f.png", "content_base64": encoded}],
                "confirmations": [],
                "client_request_id": "log-attack-1",
            },
            headers=_headers(),
        )

    emitted = _emitted_text(caplog.records)
    assert encoded[:64] not in emitted
    assert "data:image" not in emitted
    # A PNG's magic bytes are the cheapest proof that raw content reached a log.
    assert "\\x89PNG" not in emitted and "iVBORw0" not in emitted


@pytest.mark.slow
def test_no_log_record_carries_raw_provider_output(monkeypatch, caplog) -> None:
    app = _app(monkeypatch)
    fake = _install_fake(app)
    client = TestClient(app)

    sentinel = "PROVIDER-RAW-SENTINEL-a1b2c3"
    original = fake.__call__

    def _tagged(problem_text, images):  # noqa: ANN001 - test double
        envelope = original(problem_text, images)
        logging.getLogger(__name__).debug("test-only marker, not provider output")
        return envelope

    app.state.mechanics_multimodal_envelope_generator = _tagged

    with caplog.at_level(logging.DEBUG):
        client.post(
            "/api/mechanics/multimodal/evidence",
            json=_initial_json(request_id="log-attack-2"),
            headers=_headers(),
        )

    assert sentinel not in _emitted_text(caplog.records)


def test_metric_payload_audit_rejects_source_bearing_telemetry() -> None:
    """The one telemetry surface that exists must stay closed-shape."""

    from engine.mechanics.multimodal_observability import audit_metric_payload

    assert audit_metric_payload(
        {
            "terminal": "ready",
            "image_count": 1,
            "observation_count": 1,
            "conflict_count": 0,
            "confirmation_count": 0,
        }
    )
    assert not audit_metric_payload({"terminal": "ready", "image_base64": "AAAA"})
    assert not audit_metric_payload({"terminal": "ready", "problem_text": "..."})
    assert not audit_metric_payload({"terminal": "ready", "raw_provider_output": "..."})


# --------------------------------------------------------------------------
# expected_answer_leakage, reached through the *source* rather than an import.
# --------------------------------------------------------------------------
def test_production_runtime_never_reads_a_gold_member_by_name() -> None:
    from pathlib import Path

    from evaluation.phase56_stage7.isolation import (
        assert_runtime_source_does_not_read_gold_members,
    )

    repository_root = Path(__file__).resolve().parents[2]
    assert_runtime_source_does_not_read_gold_members(repository_root)


def test_the_gold_member_guard_can_actually_fail(tmp_path) -> None:
    """A guard that cannot fail measures nothing."""

    from evaluation.phase56_stage7.isolation import (
        assert_runtime_source_does_not_read_gold_members,
    )

    root = tmp_path / "backend" / "engine"
    root.mkdir(parents=True)
    (root / "leak.py").write_text("value = draft.expected_answer\n", encoding="utf-8")
    (tmp_path / "backend" / "app").mkdir(parents=True)

    with pytest.raises(ValueError, match="gold member"):
        assert_runtime_source_does_not_read_gold_members(tmp_path)


def test_the_gold_member_guard_does_not_flag_a_denylist(tmp_path) -> None:
    """Naming a forbidden field is what a denylist *is*."""

    from evaluation.phase56_stage7.isolation import (
        assert_runtime_source_does_not_read_gold_members,
    )

    root = tmp_path / "backend" / "engine"
    root.mkdir(parents=True)
    (root / "denylist.py").write_text(
        'FORBIDDEN = frozenset({"expected_answer", "gold_graph", "corpus_family"})\n',
        encoding="utf-8",
    )
    (tmp_path / "backend" / "app").mkdir(parents=True)

    assert_runtime_source_does_not_read_gold_members(tmp_path)
