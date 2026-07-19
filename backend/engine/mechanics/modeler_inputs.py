"""Trusted caller input contracts for text-plus-still-image modeling."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata

from engine.mechanics.contracts import SourceAsset
from engine.mechanics.modeler_config import MechanicsModelerConfig


STILL_IMAGE_MEDIA_TYPES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ModelerInputError(ValueError):
    """A privacy-safe preflight failure raised before any model call."""

    code = "input_invalid"


class ModelerFigureDisabledError(ModelerInputError):
    code = "figure_disabled"


class ModelerInputBudgetError(ModelerInputError):
    code = "input_budget_exceeded"


def _sanitized_input_error(error: BaseException) -> ModelerInputError:
    """Clone only the safe input-failure subtype; never retain raw arguments."""

    if isinstance(error, ModelerFigureDisabledError):
        cloned: ModelerInputError = ModelerFigureDisabledError(
            "figure input is disabled"
        )
    elif isinstance(error, ModelerInputBudgetError):
        cloned = ModelerInputBudgetError("modeler input budget was exceeded")
    else:
        cloned = ModelerInputError("modeler input is invalid")
    cloned.__cause__ = None
    cloned.__context__ = None
    cloned.__traceback__ = None
    cloned.__suppress_context__ = True
    return cloned


@dataclass(frozen=True)
class ModelerImageInput:
    """A caller-bound image whose content identity is verified before dispatch."""

    asset_id: str
    content_sha256: str
    media_type: str
    data: bytes = field(repr=False)
    page_id: str | None = None
    page_number: int | None = None
    parent_asset_id: str | None = None

    def verified_asset(self, config: MechanicsModelerConfig) -> SourceAsset:
        sanitized_error: ModelerInputError | None = None
        try:
            result = self._verified_asset_raw(config)
        except Exception as caught:
            sanitized_error = _sanitized_input_error(caught)
        if sanitized_error is None:
            return result

        error = sanitized_error
        sanitized_error = None
        self = None  # type: ignore[assignment]
        config = None  # type: ignore[assignment]
        error.__cause__ = None
        error.__context__ = None
        error.__traceback__ = None
        error.__suppress_context__ = True
        raise error from None

    def _verified_asset_raw(self, config: MechanicsModelerConfig) -> SourceAsset:
        if not isinstance(self.data, bytes):
            raise ModelerInputError("image data must be immutable bytes")
        if not isinstance(self.asset_id, str) or not _IDENTIFIER.fullmatch(self.asset_id):
            raise ModelerInputError("image asset identity is invalid")
        for optional_id in (self.page_id, self.parent_asset_id):
            if optional_id is not None and (
                not isinstance(optional_id, str) or not _IDENTIFIER.fullmatch(optional_id)
            ):
                raise ModelerInputError("image page identity is invalid")
        if self.page_number is not None and (
            not isinstance(self.page_number, int)
            or isinstance(self.page_number, bool)
            or not 1 <= self.page_number <= 100_000
        ):
            raise ModelerInputError("image page number is invalid")
        if not isinstance(self.media_type, str) or self.media_type not in STILL_IMAGE_MEDIA_TYPES:
            raise ModelerInputError("image media type is not allowed")
        if not self.data:
            raise ModelerInputError("image data is empty")
        if len(self.data) > config.max_image_bytes:
            raise ModelerInputBudgetError("image exceeds the byte budget")
        digest = hashlib.sha256(self.data).hexdigest()
        if not isinstance(self.content_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.content_sha256
        ):
            raise ModelerInputError("image content identity is invalid")
        if digest != self.content_sha256:
            raise ModelerInputError("image content identity does not match bytes")
        if not _matches_signature(self.media_type, self.data):
            raise ModelerInputError("image bytes do not match the declared media type")
        return SourceAsset(
            asset_id=self.asset_id,
            kind="image",
            content_sha256=digest,
            media_type=self.media_type,
            page_id=self.page_id,
            page_number=self.page_number,
            parent_asset_id=self.parent_asset_id,
        )


@dataclass(frozen=True)
class VerifiedModelerInput:
    problem_text: str = field(repr=False)
    normalized_text_sha256: str
    source_text_sha256: str
    images: tuple[ModelerImageInput, ...] = field(repr=False)
    assets: tuple[SourceAsset, ...]


def _matches_signature(media_type: str, data: bytes) -> bool:
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if media_type == "image/gif":
        return _static_gif(data)
    return False


def _static_gif(data: bytes) -> bool:
    """Accept a well-framed GIF with exactly one image descriptor."""
    if len(data) < 14 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        return False
    packed = data[10]
    offset = 13
    if packed & 0x80:
        offset += 3 * (2 ** ((packed & 0x07) + 1))
    frames = 0

    def skip_sub_blocks(position: int) -> int | None:
        while position < len(data):
            size = data[position]
            position += 1
            if size == 0:
                return position
            position += size
            if position > len(data):
                return None
        return None

    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            return frames == 1
        if marker == 0x21:
            if offset >= len(data):
                return False
            offset += 1  # extension label
            next_offset = skip_sub_blocks(offset)
            if next_offset is None:
                return False
            offset = next_offset
            continue
        if marker != 0x2C or offset + 9 > len(data):
            return False
        frames += 1
        if frames > 1:
            return False
        descriptor_packed = data[offset + 8]
        offset += 9
        if descriptor_packed & 0x80:
            offset += 3 * (2 ** ((descriptor_packed & 0x07) + 1))
        if offset >= len(data):
            return False
        offset += 1  # LZW minimum code size
        next_offset = skip_sub_blocks(offset)
        if next_offset is None:
            return False
        offset = next_offset
    return False


def normalized_text(problem_text: str) -> str:
    # Preserve exact source text separately for evidence offsets.  This value is
    # only a stable cache/hash projection and never replaces the source string.
    return " ".join(unicodedata.normalize("NFKC", problem_text).split())


def verify_modeler_input(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    config: MechanicsModelerConfig,
) -> VerifiedModelerInput:
    sanitized_error: ModelerInputError | None = None
    try:
        result = _verify_modeler_input_raw(problem_text, images, config)
    except Exception as caught:
        sanitized_error = _sanitized_input_error(caught)
    if sanitized_error is None:
        return result

    error = sanitized_error
    sanitized_error = None
    problem_text = ""
    images = ()
    config = None  # type: ignore[assignment]
    error.__cause__ = None
    error.__context__ = None
    error.__traceback__ = None
    error.__suppress_context__ = True
    raise error from None


def _verify_modeler_input_raw(
    problem_text: str,
    images: tuple[ModelerImageInput, ...],
    config: MechanicsModelerConfig,
) -> VerifiedModelerInput:
    if not isinstance(problem_text, str) or not problem_text.strip():
        raise ModelerInputError("problem text must be non-empty")
    try:
        source_bytes = problem_text.encode("utf-8")
    except UnicodeEncodeError:
        raise ModelerInputError("problem text is not valid UTF-8") from None
    if len(problem_text) > config.max_problem_chars:
        raise ModelerInputBudgetError("problem exceeds the character budget")
    if len(images) > config.max_images:
        raise ModelerInputBudgetError("image count exceeds the budget")
    if any(not isinstance(image, ModelerImageInput) for image in images):
        raise ModelerInputError("every image must use the typed modeler input contract")
    if images and not config.figure_enabled:
        raise ModelerFigureDisabledError("figure modeling is disabled")
    assets = tuple(image._verified_asset_raw(config) for image in images)
    if len({asset.asset_id for asset in assets}) != len(assets):
        raise ModelerInputError("image asset identities must be unique")
    if sum(len(image.data) for image in images) > config.max_total_image_bytes:
        raise ModelerInputBudgetError("total image bytes exceed the budget")
    exact_hash = hashlib.sha256(source_bytes).hexdigest()
    normalized_hash = hashlib.sha256(
        normalized_text(problem_text).encode("utf-8")
    ).hexdigest()
    return VerifiedModelerInput(
        problem_text=problem_text,
        normalized_text_sha256=normalized_hash,
        source_text_sha256=exact_hash,
        images=images,
        assets=assets,
    )


__all__ = [
    "ModelerFigureDisabledError",
    "ModelerImageInput",
    "ModelerInputBudgetError",
    "ModelerInputError",
    "STILL_IMAGE_MEDIA_TYPES",
    "VerifiedModelerInput",
    "normalized_text",
    "verify_modeler_input",
]
