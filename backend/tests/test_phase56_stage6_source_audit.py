from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE6_SOURCES = (
    ROOT / "engine" / "mechanics" / "image_security.py",
    ROOT / "engine" / "mechanics" / "evidence_reconciliation.py",
    ROOT / "engine" / "mechanics" / "multimodal_modeler.py",
    ROOT / "engine" / "mechanics" / "multimodal_revision.py",
    ROOT / "engine" / "mechanics" / "multimodal_idempotency.py",
    ROOT / "engine" / "mechanics" / "multimodal_service.py",
    ROOT / "engine" / "mechanics" / "multimodal_provider.py",
    ROOT / "engine" / "mechanics" / "multimodal_runtime.py",
    ROOT / "app" / "mechanics_multimodal_router.py",
)


def test_stage6_has_no_ocr_or_implicit_live_model_client() -> None:
    forbidden = (
        "pytesseract",
        "easyocr",
        "google.cloud.vision",
        "anthropic(",
        "requests.post(",
        "httpx.post(",
    )
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in STAGE6_SOURCES)
    for token in forbidden:
        assert token not in combined

    provider = (ROOT / "engine" / "mechanics" / "multimodal_provider.py").read_text(encoding="utf-8")
    assert 'MECHANICS_MULTIMODAL_PROVIDER' in provider
    assert 'if not provider or provider in {"off", "disabled", "none"}' in provider
    assert 'store=False' in provider
    assert 'max_retries=0' in provider


def test_temporary_stage6_mutating_workflows_are_absent() -> None:
    workflows = ROOT.parent / ".github" / "workflows"
    assert not (workflows / "phase56-workspace-export.yml").exists()
    assert not (workflows / "phase56-stage6-finalize.yml").exists()
