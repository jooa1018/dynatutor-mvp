from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE6_SOURCES = (
    ROOT / "engine" / "mechanics" / "image_security.py",
    ROOT / "engine" / "mechanics" / "evidence_reconciliation.py",
    ROOT / "engine" / "mechanics" / "multimodal_modeler.py",
    ROOT / "engine" / "mechanics" / "multimodal_revision.py",
    ROOT / "engine" / "mechanics" / "multimodal_service.py",
    ROOT / "app" / "mechanics_multimodal_router.py",
)


def test_stage6_has_no_ocr_or_implicit_live_model_client() -> None:
    forbidden = (
        "pytesseract",
        "easyocr",
        "google.cloud.vision",
        "openai(",
        "anthropic(",
        "requests.post(",
        "httpx.post(",
    )
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in STAGE6_SOURCES)
    for token in forbidden:
        assert token not in combined


def test_temporary_workspace_export_workflow_is_absent() -> None:
    assert not (ROOT.parent / ".github" / "workflows" / "phase56-workspace-export.yml").exists()
