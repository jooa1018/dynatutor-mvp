# Phase 36: Pre-deploy cleanup and parser hardening

## Repo/zip hygiene

- Runtime SQLite databases are excluded from source and release zips.
- `backend/dynatutor_records.sqlite`, `*.sqlite`, `*.sqlite3`, and `*.db` are ignored.
- The actual notebook DB is created automatically at `DYNATUTOR_DB` when the backend writes records.
- Render free deployment uses `DYNATUTOR_DB=/tmp/dynatutor_records.sqlite`; this is ephemeral and resets on restart/redeploy. Use a paid persistent disk only if you intentionally switch to a durable path.

## Token security

- `NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN` must not appear in `.env.example` or frontend code.
- The browser token is entered by the user in the UI and stored in localStorage only.
- Protected APIs use `x-dynatutor-token` or `Authorization: Bearer ...`. Query-string token auth is unsupported.
- `/records/export` is fetched with header auth and downloaded as a blob.

## Frontend deployment

- Node 20 is pinned by `frontend/.nvmrc`, `frontend/.node-version`, and `package.json#engines`.
- Vercel should use `npm ci` and `npm run build`; `frontend/scripts/build-static.js` writes the static output to `out/`.

## Parser regressions

- `완전탄성충돌` sets `collision=True`, `elastic=True`, and no longer sets `spring=True`.
- Spring routing requires explicit spring/용수철 or elastic-potential-energy wording.
- Korean table-hanging pulley cues now include table/desk/horizontal-surface, string/rope connection, and hanging-mass phrases.
- If table-hanging friction is omitted, the app asks a clarification instead of silently assuming frictionless.
