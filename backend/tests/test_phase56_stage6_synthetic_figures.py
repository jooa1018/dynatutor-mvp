from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from engine.mechanics.image_security import sanitize_image
from tests.support.synthetic_mechanics_figures import (
    free_body_diagram,
    incline_diagram,
    pulley_diagram,
)


def test_synthetic_figures_decode_and_sanitize() -> None:
    fixtures = (incline_diagram(), pulley_diagram(), free_body_diagram())
    for index, raw in enumerate(fixtures):
        source = Image.open(BytesIO(raw))
        assert source.format == "PNG"
        sanitized = sanitize_image(
            raw,
            image_id=f"synthetic_{index}",
            image_index=index,
            declared_media_type="image/png",
        )
        assert sanitized.width > 0
        assert sanitized.height > 0
        assert sanitized.content_sha256


def test_manifest_is_synthetic_only_and_has_broad_conflict_coverage() -> None:
    path = Path(__file__).parent / "fixtures" / "phase56_stage6_synthetic_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["source_policy"] == "synthetic_only"
    assert len(manifest["cases"]) >= 12
    assert {item["family"] for item in manifest["cases"]} == {
        "incline",
        "pulley",
        "free_body",
    }
    assert sum(item["relation"] == "conflict" for item in manifest["cases"]) >= 5
