from __future__ import annotations

import os
from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.mechanics_multimodal_router import router as mechanics_multimodal_router
from app.middleware.personal_auth import PersonalAccessTokenMiddleware
from app.middleware.runtime_limits import (
    MULTIMODAL_PROTECTED_PREFIX,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    configured_max_body_bytes,
    configured_multimodal_wire_body_bytes,
    configured_rate_limit,
)
from app.routes.diagnose import router as diagnose_router
from app.routes.examples import router as examples_router
from app.routes.explain import router as explain_router
from app.routes.feedback import router as feedback_router
from app.routes.records import router as records_router
from app.routes.solve import router as solve_router
from app.routes.study import router as study_router
from engine.mechanics.multimodal_provider import (
    MultimodalProviderError,
    build_multimodal_generator_from_environment,
)
from engine.mechanics.multimodal_revision import RevisionStore


def _is_production() -> bool:
    return (
        os.environ.get("DYNATUTOR_ENV", "").strip().lower() == "production"
        or os.environ.get("RENDER", "").strip().lower() in {"true", "1"}
    )


def _enforce_production_token() -> None:
    """Refuse to expose the production API without its personal access token."""

    if _is_production() and not os.environ.get("DYNATUTOR_ACCESS_TOKEN", "").strip():
        raise RuntimeError(
            "DYNATUTOR_ACCESS_TOKEN 이 설정되지 않았습니다. "
            "production 환경에서는 개인용 접근 토큰 없이 서버를 공개할 수 없습니다. "
            "Render 대시보드의 Environment 에 DYNATUTOR_ACCESS_TOKEN 을 추가하세요."
        )


def _public_docs_enabled() -> bool:
    """Keep docs open locally and closed by default in production/Render."""

    raw = os.environ.get("DYNATUTOR_PUBLIC_DOCS")
    if raw is None:
        return not _is_production()
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _configured_cors_origins(override: Sequence[str] | None = None) -> list[str]:
    if override is not None:
        origins = [str(item).strip() for item in override if str(item).strip()]
        return origins or ["*"]
    raw = os.environ.get("DYNATUTOR_CORS_ORIGINS", "*")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["*"]


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} is outside the bounded range")
    return value


def _configure_multimodal_state(application: FastAPI) -> None:
    application.state.mechanics_multimodal_revision_store = RevisionStore(
        ttl_seconds=_bounded_int(
            "MECHANICS_MULTIMODAL_REVISION_TTL_SECONDS", 900, 60, 86_400
        ),
        max_entries=_bounded_int(
            "MECHANICS_MULTIMODAL_REVISION_MAX_ENTRIES", 256, 1, 4096
        ),
    )
    application.state.mechanics_multimodal_event_sink = None
    application.state.mechanics_multimodal_provider_error = None
    try:
        generator = build_multimodal_generator_from_environment()
    except MultimodalProviderError as exc:
        # Configuration is explicit, but an unavailable provider must fail closed at
        # request time instead of preventing the deterministic text-only app from booting.
        generator = None
        application.state.mechanics_multimodal_provider_error = {
            "code": exc.code,
            "message": str(exc),
        }
    application.state.mechanics_multimodal_envelope_generator = generator


def create_app(*, cors_override: Sequence[str] | None = None) -> FastAPI:
    _enforce_production_token()
    docs_enabled = _public_docs_enabled()
    application = FastAPI(
        title="DynaTutor API",
        version="0.1.0",
        description="동역학 문제 진단, solver 선택, 검산, 단계별 풀이 카드 생성 API",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # These are installed before CORS/auth so the final middleware order remains:
    # CORS -> auth -> rate -> pre-parser body bound -> route.
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=configured_max_body_bytes(),
        path_limits={
            MULTIMODAL_PROTECTED_PREFIX: configured_multimodal_wire_body_bytes(),
        },
    )
    application.add_middleware(
        RateLimitMiddleware,
        requests_per_window=configured_rate_limit(),
    )
    application.add_middleware(PersonalAccessTokenMiddleware)

    origins = _configured_cors_origins(cors_override)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=("*" not in origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(diagnose_router, prefix="/diagnose", tags=["diagnose"])
    application.include_router(solve_router, prefix="/solve", tags=["solve"])
    application.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
    application.include_router(records_router, prefix="/records", tags=["records"])
    application.include_router(examples_router, prefix="/examples", tags=["examples"])
    application.include_router(explain_router, prefix="/explain", tags=["explain"])
    application.include_router(study_router, prefix="/study", tags=["study"])
    # Stage 6 is registered directly in source exactly once. No workflow mutates main.py.
    application.include_router(mechanics_multimodal_router)

    _configure_multimodal_state(application)

    @application.get("/")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "name": "DynaTutor API",
            "message": "POST /diagnose, /solve 또는 /api/mechanics/multimodal/evidence 를 사용하세요.",
        }

    return application


_enforce_production_token()
cors_origins = _configured_cors_origins()
app = create_app(cors_override=cors_origins)


__all__ = [
    "app",
    "cors_origins",
    "create_app",
    "_enforce_production_token",
    "_public_docs_enabled",
]
