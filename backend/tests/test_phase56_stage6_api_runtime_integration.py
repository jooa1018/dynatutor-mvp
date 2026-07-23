from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.middleware.runtime_limits import RequestBodyLimitMiddleware
from engine.mechanics.image_security import RawImageInput, sanitize_images
from engine.mechanics.multimodal_provider import (
    MultimodalProviderConfig,
    OpenAIMultimodalEnvelopeGenerator,
    build_multimodal_generator_from_environment,
)
from tests.support.stage6_multimodal_fixtures import (
    FORCE_PROBLEM_TEXT,
    force_envelope,
    synthetic_png,
)


@dataclass
class FakeEnvelopeGenerator:
    calls: list[tuple[str, tuple[str, ...]]]

    def __call__(self, problem_text, images):
        self.calls.append((problem_text, tuple(item.content_sha256 for item in images)))
        return force_envelope(problem_text=problem_text, images=images)


def _app(monkeypatch, *, token: str | None = None, rate: int = 0, wire: int = 30 * 1024 * 1024):
    monkeypatch.delenv("MECHANICS_MULTIMODAL_PROVIDER", raising=False)
    monkeypatch.setenv("DYNATUTOR_RATE_LIMIT_PER_MINUTE", str(rate))
    monkeypatch.setenv("DYNATUTOR_MULTIMODAL_MAX_WIRE_BYTES", str(wire))
    monkeypatch.setenv("DYNATUTOR_MAX_BODY_BYTES", "65536")
    monkeypatch.delenv("DYNATUTOR_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    if token is None:
        monkeypatch.delenv("DYNATUTOR_ACCESS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DYNATUTOR_ACCESS_TOKEN", token)
    return create_app(cors_override=["https://frontend.test"])


def _install_fake(app):
    fake = FakeEnvelopeGenerator([])
    app.state.mechanics_multimodal_envelope_generator = fake
    return fake


def _headers(*, token: str | None = None, session: str = "session-a") -> dict[str, str]:
    result = {"x-dynatutor-session": session}
    if token is not None:
        result["x-dynatutor-token"] = token
    return result


def _initial_json(*, request_id: str = "initial-1") -> dict[str, Any]:
    return {
        "problem_text": FORCE_PROBLEM_TEXT,
        "images": [],
        "confirmations": [],
        "client_request_id": request_id,
    }


def test_openapi_registers_stage6_routes_exactly_once_and_unconfigured_is_typed_503(monkeypatch) -> None:
    app = _app(monkeypatch)
    paths = app.openapi()["paths"]
    assert "/api/mechanics/multimodal/evidence" in paths
    assert sum(
        1
        for route in app.routes
        if getattr(route, "path", None) == "/api/mechanics/multimodal/evidence"
        and "POST" in getattr(route, "methods", set())
    ) == 1
    expected = {
        "/api/mechanics/multimodal/evidence",
        "/api/mechanics/multimodal/revisions/{revision_id}",
        "/api/mechanics/multimodal/revisions/{revision_id}/confirm",
        "/api/mechanics/multimodal/revisions/{revision_id}/correct",
        "/api/mechanics/multimodal/revisions/{revision_id}/execute",
    }
    assert expected.issubset(paths)

    response = TestClient(app).post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "multimodal_modeler_unavailable"


def test_fake_generator_runs_once_idempotently_and_deterministic_runtime_solves(monkeypatch) -> None:
    app = _app(monkeypatch)
    fake = _install_fake(app)
    client = TestClient(app)
    first = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(),
        headers=_headers(),
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["terminal"] == "solved"
    assert payload["runtime"]["terminal"] == "solved"
    assert payload["verified_answer"]["value_si"] == 5.0
    assert payload["runtime"]["equation_count"] == 1
    assert len(fake.calls) == 1

    repeated = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(),
        headers=_headers(),
    )
    assert repeated.status_code == 200
    assert repeated.json()["revision_id"] == payload["revision_id"]
    assert len(fake.calls) == 1


def test_multipart_sanitizes_four_images_and_rejects_duplicate_content(monkeypatch) -> None:
    app = _app(monkeypatch)
    fake = _install_fake(app)
    client = TestClient(app)
    files = [
        ("images", (f"figure-{index}.png", synthetic_png(label=f"F{index}"), "image/png"))
        for index in range(4)
    ]
    fields = {"problem_text": FORCE_PROBLEM_TEXT, "client_request_id": "multipart-four"}
    response = client.post(
        "/api/mechanics/multimodal/evidence",
        data=fields,
        files=files,
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["terminal"] == "solved"
    assert len(response.json()["sanitized_images"]) == 4
    assert len(fake.calls) == 1
    assert len(fake.calls[0][1]) == 4

    duplicate = synthetic_png(label="same")
    response = client.post(
        "/api/mechanics/multimodal/evidence",
        data={"problem_text": FORCE_PROBLEM_TEXT, "client_request_id": "duplicate"},
        files=[
            ("images", ("one.png", duplicate, "image/png")),
            ("images", ("two.png", duplicate, "image/png")),
        ],
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "duplicate_image_content"


def test_source_only_correction_is_revisioned_idempotent_and_reruns_runtime(monkeypatch) -> None:
    app = _app(monkeypatch)
    _install_fake(app)
    client = TestClient(app)
    initial = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(request_id="correction-base"),
        headers=_headers(),
    ).json()
    revision_id = initial["revision_id"]
    correction = {
        "schema": "dynatutor.mechanics_correction_request",
        "version": "1.0",
        "request_id": "correction-20n",
        "client_request_id": "correction-20n",
        "base_revision_id": revision_id,
        "base_revision_fingerprint": initial["revision_fingerprint"],
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
    corrected = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=correction,
        headers=_headers(),
    )
    assert corrected.status_code == 200, corrected.text
    payload = corrected.json()
    assert payload["terminal"] == "solved"
    assert payload["revision_number"] == 1
    assert payload["parent_revision_id"] == revision_id
    assert payload["verified_answer"]["value_si"] == 10.0
    assert payload["corrections_applied"][0]["kind"] == "replace_quantity_value"

    replay = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=correction,
        headers=_headers(),
    )
    assert replay.status_code == 200
    assert replay.json()["revision_id"] == payload["revision_id"]

    stale = dict(correction)
    stale["request_id"] = "stale-correction"
    stale["client_request_id"] = "stale-correction"
    stale["base_revision_fingerprint"] = "0" * 64
    response = client.post(
        f"/api/mechanics/multimodal/revisions/{revision_id}/correct",
        json=stale,
        headers=_headers(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_stale"

    isolated = client.get(
        f"/api/mechanics/multimodal/revisions/{revision_id}",
        headers=_headers(session="session-b"),
    )
    assert isolated.status_code == 404
    assert isolated.json()["detail"]["code"] == "revision_not_found"


def test_auth_rate_wire_cors_and_production_docs_policies_apply(monkeypatch) -> None:
    app = _app(monkeypatch, token="top-secret", rate=1, wire=1024)
    fake = _install_fake(app)
    client = TestClient(app)

    unauthorized = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(),
        headers={"Origin": "https://frontend.test"},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == "https://frontend.test"

    allowed_headers = _headers(token="top-secret") | {"Origin": "https://frontend.test"}
    first = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(request_id="rate-one"),
        headers=allowed_headers,
    )
    assert first.status_code == 200
    assert first.headers["access-control-allow-origin"] == "https://frontend.test"
    assert len(fake.calls) == 1
    limited = client.post(
        "/api/mechanics/multimodal/evidence",
        json=_initial_json(request_id="rate-two"),
        headers=allowed_headers,
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limit_exceeded"

    body_app = _app(monkeypatch, wire=256)
    response = TestClient(body_app).post(
        "/api/mechanics/multimodal/evidence",
        content=b"x" * 257,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "request_body_too_large"

    monkeypatch.setenv("DYNATUTOR_ENV", "production")
    monkeypatch.setenv("DYNATUTOR_ACCESS_TOKEN", "prod-token")
    monkeypatch.delenv("DYNATUTOR_PUBLIC_DOCS", raising=False)
    production = create_app(cors_override=["https://frontend.test"])
    assert production.docs_url is None
    assert production.openapi_url is None


def test_wire_limit_counts_chunked_bytes_without_content_length() -> None:
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    middleware = RequestBodyLimitMiddleware(
        downstream,
        max_body_bytes=0,
        path_limits={"/api/mechanics/multimodal": 8},
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/mechanics/multimodal/evidence",
        "raw_path": b"/api/mechanics/multimodal/evidence",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("test", 123),
        "server": ("test", 80),
    }
    incoming = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive():
        return next(incoming)

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    assert called is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


def test_base64_expansion_total_overflow_and_corrupted_multipart_fail_closed(monkeypatch) -> None:
    app = _app(monkeypatch)
    _install_fake(app)
    client = TestClient(app)

    oversized_raw = b"x" * (8 * 1024 * 1024 + 1)
    encoded = base64.b64encode(oversized_raw).decode("ascii")
    response = client.post(
        "/api/mechanics/multimodal/evidence",
        json={
            "problem_text": FORCE_PROBLEM_TEXT,
            "images": [
                {
                    "image_id": "too-large",
                    "media_type": "image/png",
                    "data_base64": encoded,
                }
            ],
            "confirmations": [],
            "client_request_id": "base64-expansion",
        },
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "image_bytes_exceeded"

    seven_mib = b"x" * (7 * 1024 * 1024)
    response = client.post(
        "/api/mechanics/multimodal/evidence",
        data={"problem_text": FORCE_PROBLEM_TEXT, "client_request_id": "total-overflow"},
        files=[
            ("images", (f"image-{index}.png", seven_mib, "image/png"))
            for index in range(3)
        ],
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "total_image_bytes_exceeded"

    response = client.post(
        "/api/mechanics/multimodal/evidence",
        content=b"this is not a multipart document",
        headers=_headers() | {"content-type": "multipart/form-data; boundary=missing"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_multipart"


def test_provider_adapter_is_explicit_private_bounded_and_combined(monkeypatch) -> None:
    monkeypatch.delenv("MECHANICS_MULTIMODAL_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-probed")
    assert build_multimodal_generator_from_environment() is None

    raw_images = (
        RawImageInput("image1", synthetic_png(label="one"), "image/png"),
        RawImageInput("image2", synthetic_png(label="two"), "image/png"),
    )
    images = sanitize_images(raw_images)
    envelope = force_envelope(images=images)

    calls: list[dict[str, Any]] = []

    class Responses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output_parsed=envelope)

    client = SimpleNamespace(responses=Responses())
    generator = OpenAIMultimodalEnvelopeGenerator(
        MultimodalProviderConfig(
            provider="openai",
            model="fixed-test-model",
            timeout_seconds=12.0,
            max_output_tokens=2048,
            max_repairs=1,
        ),
        client=client,
    )
    result = generator(FORCE_PROBLEM_TEXT, images)
    assert result == envelope
    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "fixed-test-model"
    assert call["store"] is False
    assert call["tools"] == []
    assert call["max_output_tokens"] == 2048
    content = call["input"][0]["content"]
    assert sum(item["type"] == "input_text" for item in content) == 1
    assert sum(item["type"] == "input_image" for item in content) == 2


def test_provider_repair_is_at_most_one_fresh_full_attempt() -> None:
    image = sanitize_images((RawImageInput("image1", synthetic_png(), "image/png"),))[0]
    envelope = force_envelope(images=(image,))
    calls: list[dict[str, Any]] = []

    class Responses:
        def parse(self, **kwargs):
            calls.append(kwargs)
            parsed = None if len(calls) == 1 else envelope
            return SimpleNamespace(status="completed", output_parsed=parsed)

    generator = OpenAIMultimodalEnvelopeGenerator(
        MultimodalProviderConfig("openai", "fixed-test-model", 12.0, 2048, 1),
        client=SimpleNamespace(responses=Responses()),
    )
    assert generator(FORCE_PROBLEM_TEXT, (image,)) == envelope
    assert len(calls) == 2
    repair_text = calls[1]["input"][0]["content"][0]["text"]
    assert "fresh complete envelope" in repair_text
    assert "raw invalid response" in repair_text
