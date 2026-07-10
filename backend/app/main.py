import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.personal_auth import PersonalAccessTokenMiddleware

from app.routes.diagnose import router as diagnose_router
from app.routes.solve import router as solve_router
from app.routes.feedback import router as feedback_router
from app.routes.records import router as records_router
from app.routes.examples import router as examples_router
from app.routes.explain import router as explain_router
from app.routes.study import router as study_router

def _enforce_production_token() -> None:
    """production 환경에서 접근 토큰 없이 서버가 공개로 열리는 것을 차단.

    Render는 RENDER=true 를 자동 주입하고, render.yaml 은 DYNATUTOR_ENV=production
    을 설정한다. 둘 중 하나라도 감지되면 토큰이 필수다.
    로컬 개발(둘 다 미설정)은 기존처럼 토큰 없이 동작한다.
    """
    is_production = (
        os.environ.get("DYNATUTOR_ENV", "").lower() == "production"
        or os.environ.get("RENDER", "").lower() in ("true", "1")
    )
    if is_production and not os.environ.get("DYNATUTOR_ACCESS_TOKEN", "").strip():
        raise RuntimeError(
            "DYNATUTOR_ACCESS_TOKEN 이 설정되지 않았습니다. "
            "production 환경에서는 개인용 접근 토큰 없이 서버를 공개할 수 없습니다. "
            "Render 대시보드의 Environment 에 DYNATUTOR_ACCESS_TOKEN 을 추가하세요."
        )


_enforce_production_token()


def _public_docs_enabled() -> bool:
    """API 문서 공개 여부.

    개발 환경은 기본 공개, production/Render는 기본 비공개다.
    DYNATUTOR_PUBLIC_DOCS=true 로 명시하면 production에서도 열 수 있다.
    """
    raw = os.environ.get("DYNATUTOR_PUBLIC_DOCS")
    is_production = (
        os.environ.get("DYNATUTOR_ENV", "").lower() == "production"
        or os.environ.get("RENDER", "").lower() in ("true", "1")
    )
    if raw is None:
        return not is_production
    return raw.strip().lower() in ("1", "true", "yes", "on")


_docs_enabled = _public_docs_enabled()

app = FastAPI(
    title="DynaTutor API",
    version="0.1.0",
    description="동역학 문제 진단, solver 선택, 검산, 단계별 풀이 카드 생성 API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

cors_origins_raw = os.environ.get("DYNATUTOR_CORS_ORIGINS", "*")
cors_origins = [x.strip() for x in cors_origins_raw.split(",") if x.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=("*" not in cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# If DYNATUTOR_ACCESS_TOKEN is set, useful API endpoints require a personal token.
# If unset, local development remains frictionless.
app.add_middleware(PersonalAccessTokenMiddleware)

app.include_router(diagnose_router, prefix="/diagnose", tags=["diagnose"])
app.include_router(solve_router, prefix="/solve", tags=["solve"])
app.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
app.include_router(records_router, prefix="/records", tags=["records"])
app.include_router(examples_router, prefix="/examples", tags=["examples"])
app.include_router(explain_router, prefix="/explain", tags=["explain"])
app.include_router(study_router, prefix="/study", tags=["study"])


@app.get("/")
def health() -> dict:
    return {
        "ok": True,
        "name": "DynaTutor API",
        "message": "POST /diagnose 또는 POST /solve 를 사용하세요.",
    }
