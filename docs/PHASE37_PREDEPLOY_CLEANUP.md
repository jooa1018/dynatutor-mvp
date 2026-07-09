# Phase 37: pre-deploy cleanup final pass

## DB hygiene

- Runtime DB files are not part of the repo or release zip.
- `.gitignore` excludes `*.sqlite`, `*.sqlite3`, `*.db`, and `backend/dynatutor_records.sqlite`.
- `DYNATUTOR_DB=/tmp/dynatutor_records.sqlite` is the Render free-plan default. This path is ephemeral.
- A persistent disk path such as `/data/...` should be used only when a paid Render disk is intentionally attached.

## Token security

- `NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN` is not used in `.env.example` or frontend code.
- Users enter the personal token in the app UI; the browser stores it in localStorage.
- Protected APIs use `x-dynatutor-token` or `Authorization: Bearer ...` headers.
- Query-string token authentication is unsupported; `/records/export` uses header authentication.

## Frontend build

- Node 20 is pinned through `.nvmrc`, `.node-version`, and `package.json#engines`.
- `npm run build` runs `scripts/build-static.js`, which type-checks and creates a static React bundle in `out/`.
- Vercel should use `npm ci`, `npm run build`, and output directory `out`.

## Parser regressions

- `완전탄성충돌` routes as collision/elastic only; it does not set `spring=True`.
- Spring flags require explicit spring/용수철/elastic-potential-energy wording.
- Korean table-hanging pulley expressions now detect table/desk, string/rope connection, and hanging mass cues.
- If friction is missing in a table-hanging pulley problem, the app asks for friction information instead of assuming.
