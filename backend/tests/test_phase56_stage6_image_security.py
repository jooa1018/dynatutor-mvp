from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

from engine.mechanics.image_security import (
    ImageSecurityError,
    RawImageInput,
    sanitize_image,
    sanitize_images,
)


def _png(*, metadata: bool = False, size: tuple[int, int] = (96, 64)) -> bytes:
    image = Image.new("RGB", size, "white")
    output = BytesIO()
    info = None
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("private-note", "must-not-survive")
    image.save(output, format="PNG", pnginfo=info)
    return output.getvalue()


def test_sanitizer_is_deterministic_and_strips_metadata() -> None:
    raw = _png(metadata=True)
    first = sanitize_image(raw, image_id="diagram", image_index=0, declared_media_type="image/png")
    second = sanitize_image(raw, image_id="diagram", image_index=0, declared_media_type="image/png")
    assert first.content == second.content
    assert first.content_sha256 == second.content_sha256
    assert b"private-note" not in first.content
    decoded = Image.open(BytesIO(first.content))
    assert decoded.format == "PNG"
    assert decoded.info == {}
    assert "must-not-survive" not in repr(first)


def test_media_type_mismatch_is_rejected() -> None:
    with pytest.raises(ImageSecurityError) as caught:
        sanitize_image(
            _png(),
            image_id="diagram",
            image_index=0,
            declared_media_type="image/jpeg",
        )
    assert caught.value.code == "media_type_mismatch"


def test_collection_limits_and_duplicate_ids_are_fail_closed() -> None:
    raw = _png()
    with pytest.raises(ImageSecurityError) as caught:
        sanitize_images(
            [
                RawImageInput("same", raw, "image/png"),
                RawImageInput("same", raw, "image/png"),
            ]
        )
    assert caught.value.code == "duplicate_image_id"


def test_animated_image_is_rejected_when_encoder_supports_it() -> None:
    output = BytesIO()
    frames = [Image.new("RGB", (24, 24), value) for value in ("white", "black")]
    try:
        frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], duration=20)
    except (OSError, ValueError):
        pytest.skip("Pillow build does not provide animated WebP support")
    with pytest.raises(ImageSecurityError) as caught:
        sanitize_image(
            output.getvalue(),
            image_id="animated",
            image_index=0,
            declared_media_type="image/webp",
        )
    assert caught.value.code == "animated_image_rejected"
