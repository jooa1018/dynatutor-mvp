from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import pytest
from PIL import Image

from app.middleware.runtime_limits import RequestBodyLimitMiddleware
from engine.mechanics import image_security as image_security_module
from engine.mechanics.image_security import (
    ImageSecurityError,
    RawImageInput,
    SanitizedImage,
    sanitize_image,
    sanitize_images,
)


def test_transparent_pixels_are_flattened_to_canonical_white() -> None:
    image = Image.new("RGBA", (2, 1), (255, 0, 0, 0))
    image.putpixel((1, 0), (0, 0, 0, 255))
    output = BytesIO()
    image.save(output, format="PNG")

    sanitized = sanitize_image(
        output.getvalue(),
        image_id="transparent",
        image_index=0,
        declared_media_type="image/png",
    )
    decoded = Image.open(BytesIO(sanitized.content))
    assert decoded.mode == "RGB"
    assert decoded.getpixel((0, 0)) == (255, 255, 255)
    assert decoded.getpixel((1, 0)) == (0, 0, 0)


def test_sanitized_collection_has_an_independent_total_byte_ceiling(monkeypatch) -> None:
    oversized = SanitizedImage(
        image_id="diagram",
        image_index=0,
        content=b"x" * 11,
        content_sha256="a" * 64,
        width=1,
        height=1,
    )
    monkeypatch.setattr(image_security_module, "MAX_TOTAL_IMAGE_BYTES", 10)
    monkeypatch.setattr(image_security_module, "sanitize_image", lambda *args, **kwargs: oversized)

    with pytest.raises(ImageSecurityError) as caught:
        sanitize_images([RawImageInput("diagram", b"x", "image/png")])
    assert caught.value.code == "sanitized_total_image_bytes_exceeded"


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"1"), (b"content-length", b"1")],
        [(b"content-length", b"1"), (b"transfer-encoding", b"chunked")],
        [(b"content-length", b"not-a-number")],
        [(b"content-length", b"-1")],
    ],
)
def test_ambiguous_or_invalid_request_framing_is_rejected(headers) -> None:
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
        "headers": headers,
        "client": ("test", 123),
        "server": ("test", 80),
    }
    sent: list[dict[str, Any]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    assert called is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 400
    assert b"invalid_request_framing" in sent[1]["body"]
