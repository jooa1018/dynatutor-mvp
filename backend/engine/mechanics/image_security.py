"""Fail-closed image ingestion for Phase 56 Stage 6.

Only sanitized pixels and a digest leave this boundary. The original bytes,
metadata, filenames, and EXIF payload never become model or solver inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Iterable, Sequence
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_COUNT = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_PIXELS = 16_000_000
MAX_SOURCE_EDGE = 4096
MAX_MODEL_EDGE = 2048
ALLOWED_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_FORMAT_TO_MEDIA_TYPE = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class ImageSecurityError(ValueError):
    """Controlled image rejection without echoing user bytes or metadata."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RawImageInput:
    image_id: str
    content: bytes
    declared_media_type: str | None = None


@dataclass(frozen=True, slots=True)
class SanitizedImage:
    image_id: str
    image_index: int
    content: bytes
    content_sha256: str
    width: int
    height: int
    media_type: str = "image/png"

    def __repr__(self) -> str:
        return (
            "SanitizedImage("
            f"image_id={self.image_id!r}, image_index={self.image_index}, "
            f"content_sha256={self.content_sha256!r}, width={self.width}, "
            f"height={self.height}, media_type={self.media_type!r}, "
            "content=<redacted>)"
        )


def _reject(code: str, message: str) -> None:
    raise ImageSecurityError(code, message)


def _validate_declared_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in ALLOWED_MEDIA_TYPES:
        _reject("unsupported_media_type", "Only PNG, JPEG, and WebP images are accepted.")
    return normalized


def _open_verified(raw: bytes) -> tuple[Image.Image, str]:
    bomb_warning = getattr(Image, "DecompressionBombWarning", Warning)
    bomb_error = getattr(Image, "DecompressionBombError", Exception)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", bomb_warning)
            probe = Image.open(BytesIO(raw))
            detected_format = str(probe.format or "").upper()
            width, height = probe.size
            if width <= 0 or height <= 0:
                _reject("invalid_dimensions", "The image has invalid dimensions.")
            if width > MAX_SOURCE_EDGE or height > MAX_SOURCE_EDGE:
                _reject("image_dimensions_exceeded", "The image dimensions exceed the safety limit.")
            if width * height > MAX_SOURCE_PIXELS:
                _reject("image_pixels_exceeded", "The image pixel count exceeds the safety limit.")
            if int(getattr(probe, "n_frames", 1)) != 1 or bool(getattr(probe, "is_animated", False)):
                _reject("animated_image_rejected", "Animated images are not accepted.")
            probe.verify()
        image = Image.open(BytesIO(raw))
        image.load()
        return image, detected_format
    except ImageSecurityError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, bomb_warning, bomb_error) as exc:
        raise ImageSecurityError("invalid_image", "The image could not be decoded safely.") from exc


def sanitize_image(
    raw: bytes,
    *,
    image_id: str,
    image_index: int,
    declared_media_type: str | None = None,
) -> SanitizedImage:
    """Decode, orient, resize, and re-encode one image as metadata-free PNG."""

    if not image_id or len(image_id) > 128:
        _reject("invalid_image_id", "A bounded image identifier is required.")
    if image_index < 0 or image_index >= MAX_IMAGE_COUNT:
        _reject("invalid_image_index", "The image index is outside the accepted range.")
    if not raw:
        _reject("empty_image", "The image is empty.")
    if len(raw) > MAX_IMAGE_BYTES:
        _reject("image_bytes_exceeded", "The image exceeds the per-image byte limit.")

    declared = _validate_declared_media_type(declared_media_type)
    image, detected_format = _open_verified(raw)
    detected = _FORMAT_TO_MEDIA_TYPE.get(detected_format)
    if detected is None:
        _reject("unsupported_image_format", "Only PNG, JPEG, and WebP images are accepted.")
    if declared is not None and declared != detected:
        _reject("media_type_mismatch", "The declared media type does not match the decoded image.")

    oriented = ImageOps.exif_transpose(image)
    if max(oriented.size) > MAX_MODEL_EDGE:
        oriented.thumbnail((MAX_MODEL_EDGE, MAX_MODEL_EDGE), Image.Resampling.LANCZOS)

    has_alpha = oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info
    canonical_mode = "RGBA" if has_alpha else "RGB"
    converted = oriented.convert(canonical_mode)
    clean = Image.new(canonical_mode, converted.size)
    clean.paste(converted)

    output = BytesIO()
    clean.save(output, format="PNG", optimize=False, compress_level=9)
    sanitized = output.getvalue()
    digest = sha256(sanitized).hexdigest()
    return SanitizedImage(
        image_id=image_id,
        image_index=image_index,
        content=sanitized,
        content_sha256=digest,
        width=clean.width,
        height=clean.height,
    )


def sanitize_images(images: Sequence[RawImageInput] | Iterable[RawImageInput]) -> tuple[SanitizedImage, ...]:
    items = tuple(images)
    if len(items) > MAX_IMAGE_COUNT:
        _reject("image_count_exceeded", "Too many images were supplied.")
    if sum(len(item.content) for item in items) > MAX_TOTAL_IMAGE_BYTES:
        _reject("total_image_bytes_exceeded", "The combined image bytes exceed the safety limit.")
    ids = [item.image_id for item in items]
    if len(set(ids)) != len(ids):
        _reject("duplicate_image_id", "Every image identifier must be unique.")
    sanitized = tuple(
        sanitize_image(
            item.content,
            image_id=item.image_id,
            image_index=index,
            declared_media_type=item.declared_media_type,
        )
        for index, item in enumerate(items)
    )
    digests = tuple(item.content_sha256 for item in sanitized)
    if len(set(digests)) != len(digests):
        _reject("duplicate_image_content", "Duplicate image content is not accepted.")
    return sanitized


__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "ImageSecurityError",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_COUNT",
    "MAX_MODEL_EDGE",
    "MAX_SOURCE_EDGE",
    "MAX_SOURCE_PIXELS",
    "MAX_TOTAL_IMAGE_BYTES",
    "RawImageInput",
    "SanitizedImage",
    "sanitize_image",
    "sanitize_images",
]
