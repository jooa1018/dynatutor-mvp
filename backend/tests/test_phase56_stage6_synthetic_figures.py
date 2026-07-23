from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from engine.mechanics.image_security import sanitize_image
from tests.support.synthetic_mechanics_figures import render_manifest_case


MANIFEST_PATH = Path(__file__).parent / "fixtures" / "phase56_stage6_synthetic_manifest.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_has_at_least_thirty_synthetic_raster_cases_and_required_coverage() -> None:
    manifest = _manifest()
    assert manifest["source_policy"] == "synthetic_only"
    assert manifest["runtime_receives_expected_metadata"] is False
    cases = manifest["cases"]
    assert len(cases) >= 30
    families = {item["family"] for item in cases}
    assert {
        "incline", "friction", "pulley", "rolling", "vertical_circle",
        "collision", "projectile", "work_force", "fixed_axis_rotation",
        "impulse", "spring_energy", "flat_curve", "banked_curve",
        "rigid_body_velocity", "rigid_body_acceleration", "polar_kinematics",
    }.issubset(families)
    relations = {item["relation"] for item in cases}
    assert {"conflict", "ambiguity", "security", "metamorphic", "convention"}.issubset(relations)


def test_every_manifest_case_generates_real_decodable_bounded_raster() -> None:
    cases = _manifest()["cases"]
    raw_digests: set[str] = set()
    for index, case in enumerate(cases):
        raw, media_type = render_manifest_case(case)
        raw_digests.add(sha256(raw).hexdigest())
        source = Image.open(BytesIO(raw))
        assert source.format in {"PNG", "JPEG"}
        sanitized = sanitize_image(
            raw,
            image_id=f"synthetic_{index}",
            image_index=index % 4,
            declared_media_type=media_type,
        )
        assert sanitized.width > 0
        assert sanitized.height > 0
        assert sanitized.content_sha256
        assert sanitized.media_type == "image/png"
    assert len(raw_digests) == len(cases)


def test_security_and_metamorphic_variants_are_source_only_test_metadata() -> None:
    manifest = _manifest()
    variants = {item["variant"] for item in manifest["cases"]}
    assert {
        "prompt_injection", "occlusion", "scaled_resolution", "metadata_only",
        "mirrored", "cropped_whitespace", "transparent_text",
    }.issubset(variants)
    serialized = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "expected_answer" not in serialized
    assert "problem_text" not in serialized
