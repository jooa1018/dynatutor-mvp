# Personal Deployment Guide

This guide is for private personal use.

## 1. Generate a personal access token

From project root:

```bash
python scripts/generate_access_token.py
```

Save the token.

## 2. Backend deployment

Use the root `render.yaml` or create a web service manually.

Backend settings:

```text
root directory: backend
build command: pip install -r requirements-lock.txt
start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Required env:

```text
DYNATUTOR_ACCESS_TOKEN=<your long random token>
DYNATUTOR_CORS_ORIGINS=<your frontend URL; use * only for the first smoke test>
DYNATUTOR_DB=/tmp/dynatutor_records.sqlite
DYNATUTOR_PUBLIC_DOCS=false
```


### Render free DB note

`DYNATUTOR_DB=/tmp/dynatutor_records.sqlite` is the Render free-plan setting. It is ephemeral: notebook/review records can disappear after a restart or redeploy. If records matter, use the app export button often. A paid persistent disk can use a durable path such as `/data/dynatutor_records.sqlite`, but only when you intentionally attach that disk.

### CORS setup

Initial smoke test:

```text
DYNATUTOR_CORS_ORIGINS=*
```

Final deployment:

```text
DYNATUTOR_CORS_ORIGINS=https://your-app.vercel.app
```

Do not add a trailing `/`. If the browser reports a CORS error, check the exact Vercel origin, https/http, the backend API base URL, Render cold start, and whether the issue is actually a 401 token error.

### API docs visibility

Development keeps API docs visible by default. Production/Render hides `/docs`, `/redoc`, and `/openapi.json` unless you explicitly set:

```text
DYNATUTOR_PUBLIC_DOCS=true
```

Recommended personal production value:

```text
DYNATUTOR_PUBLIC_DOCS=false
```

Optional LLM env:

```text
LLM_ENABLED=auto
LLM_PROVIDER=openai
OPENAI_API_KEY=<optional>
OPENAI_MODEL=<optional>
OPENAI_BASE_URL=https://api.openai.com/v1
```

## 3. Frontend deployment

In Vercel or similar, set the frontend root to:

```text
frontend
```

Node version: Node 20 (`frontend/.nvmrc`, `frontend/.node-version`, and `package.json#engines` all pin v20). The production build is `frontend/scripts/build-static.js`, which writes `out/`.

Build command:

```text
npm run build
```

The static build writes the deployment directory:

```text
out/
```

Frontend env:

```text
NEXT_PUBLIC_DYNATUTOR_API_BASE=<your backend URL>
```

Backward-compatible alias:

```text
NEXT_PUBLIC_API_BASE=<your backend URL>
```

Prefer `NEXT_PUBLIC_DYNATUTOR_API_BASE`.

## 4. iPhone use

1. Open the frontend URL in Safari.
2. Enter your personal access token in the token field.
3. Solve one test problem.
4. Tap Share.
5. Tap Add to Home Screen.

## 5. Test problem

```text
질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.
```

Expected answer:

```text
a = 4.905 m/s²
```

## 6. Security note

Do not put `DYNATUTOR_ACCESS_TOKEN` in any `NEXT_PUBLIC_*` frontend variable. In particular, do not create or use `NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN`. `NEXT_PUBLIC_*` values are bundled into browser JavaScript.

Preferred method:

```text
enter token once in the iPhone UI
```

## 7. Backup

Use the notebook export function from the app or API:

```text
/records/export
```

Authentication for export uses the `x-dynatutor-token` header from the app. Query-string tokens are intentionally not documented or supported.

If server DB saving fails, the frontend keeps a temporary browser `localStorage` copy for personal free deployments. This is a fallback, not a durable backup; use export for important records.
