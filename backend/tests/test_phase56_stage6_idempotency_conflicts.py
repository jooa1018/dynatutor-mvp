from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.main import create_app
from engine.mechanics.multimodal_revision import RevisionStore
from tests.support.stage6_multimodal_fixtures import FORCE_PROBLEM_TEXT, force_envelope


@dataclass
class FakeEnvelopeGenerator:
    calls: list[str]

    def __call__(self, problem_text, images):
        self.calls.append(problem_text)
        return force_envelope(problem_text=problem_text, images=images)


def _client(monkeypatch) -> tuple[TestClient, FakeEnvelopeGenerator]:
    monkeypatch.delenv("MECHANICS_MULTIMODAL_PROVIDER", raising=False)
    monkeypatch.delenv("DYNATUTOR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DYNATUTOR_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("DYNATUTOR_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("DYNATUTOR_MAX_BODY_BYTES", "65536")
    monkeypatch.setenv("DYNATUTOR_MULTIMODAL_MAX_WIRE_BYTES", str(30 * 1024 * 1024))
    app = create_app(cors_override=["https://frontend.test"])
    fake = FakeEnvelopeGenerator([])
    app.state.mechanics_multimodal_envelope_generator = fake
    return TestClient(app), fake


def _headers() -> dict[str, str]:
    return {"x-dynatutor-session": "idempotency-session"}


def _initial(*, text: str = FORCE_PROBLEM_TEXT, request_id: str = "initial-key") -> dict[str, object]:
    return {
        "problem_text": text,
        "images": [],
        "confirmations": [],
        "client_request_id": request_id,
    }


def test_initial_idempotency_key_cannot_substitute_different_source(monkeypatch) -> None:
    client, fake = _client(monkeypatch)
    first = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial(),
        headers=_headers(),
    )
    assert first.status_code == 200, first.text
    assert len(fake.calls) == 1

    replay = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial(),
        headers=_headers(),
    )
    assert replay.status_code == 200
    assert replay.json()["revision_id"] == first.json()["revision_id"]
    assert len(fake.calls) == 1

    collision = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial(text=FORCE_PROBLEM_TEXT + " Different source."),
        headers=_headers(),
    )
    assert collision.status_code == 409
    assert collision.json()["detail"]["code"] == "request_id_conflict"
    assert len(fake.calls) == 1


def test_correction_idempotency_key_cannot_substitute_different_mutation(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    initial = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial(request_id="correction-base"),
        headers=_headers(),
    ).json()
    revision_id = initial["revision_id"]

    def correction(value: str) -> dict[str, object]:
        return {
            "schema": "dynatutor.mechanics_correction_request",
            "version": "1.0",
            "request_id": "shared-correction-key",
            "client_request_id": "shared-correction-key",
            "base_revision_id": revision_id,
            "base_revision_fingerprint": initial["revision_fingerprint"],
            "operations": [
                {
                    "kind": "replace_quantity_value",
                    "operation_id": "replace-force",
                    "quantity_id": "forceA",
                    "raw_value": value,
                    "raw_unit": "N",
                }
            ],
        }

    first = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=correction("20"),
        headers=_headers(),
    )
    assert first.status_code == 200, first.text
    assert first.json()["verified_answer"]["value_si"] == 10.0

    replay = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=correction("20"),
        headers=_headers(),
    )
    assert replay.status_code == 200
    assert replay.json()["revision_id"] == first.json()["revision_id"]

    collision = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=correction("30"),
        headers=_headers(),
    )
    assert collision.status_code == 409
    assert collision.json()["detail"]["code"] == "request_id_conflict"


def test_product_router_rejects_legacy_revision_store_configuration(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.state.mechanics_multimodal_revision_store = RevisionStore()
    response = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial(request_id="legacy-store"),
        headers=_headers(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "multimodal_revision_store_unavailable"
