# Fábula — Backend API

The cloud engine behind the app. FastAPI service that turns a project (channel +
language + art style + length) into a generated video, reusing the Cuentos pipeline.

## Run (local dev)

```
run.bat            # or:  python -m uvicorn app.main:app --port 8000
```

- API root: http://127.0.0.1:8000
- **Interactive docs (try every endpoint in the browser): http://127.0.0.1:8000/docs**

## What exists (scaffold)

| Area | Endpoint | Status |
|---|---|---|
| Health | `GET /health` | real |
| Languages | `GET /catalog/languages` | real (any-language catalog) |
| Art styles | `GET /catalog/styles` | real (preset library + custom) |
| Projects | `POST/GET /projects`, `GET /projects/{id}` | real (SQLite) |
| Generate | `POST /projects/{id}/generate` | real orchestration; **stages are stubs** |
| Job status | `GET /jobs/{id}` | real (status, progress, live log, artifacts) |
| BYOK keys | `POST/GET/DELETE /keys` | real (encrypted at rest) |
| Feedback | `POST/GET /feedback` | real (admin inbox) |

Auth is a placeholder: pass an `X-User-Id` header (defaults to `demo`). Real hosted
auth (Supabase/Clerk) drops in later without changing routers.

## What's next

Wire each stage in `app/services/engine.py` to its real provider — YouTube Data API
(analyze), LLM (script), Fish/others (audio), image API (images), the render worker
(video) — using the user's BYOK key from the vault. Then swap SQLite → Postgres and
the in-process worker → a real queue, and deploy.

## Layout

```
app/
  main.py          FastAPI app + routes wiring
  config.py        env settings
  db.py            SQLite data layer (swap for Postgres later)
  security.py      Fernet encryption for BYOK keys
  catalog.py       LANGUAGES + STYLE_PRESETS  <- 'any language, any style'
  models.py        request/response schemas
  deps.py          auth placeholder (X-User-Id)
  routers/         catalog, projects, keys, feedback
  services/        engine.py (pipeline stages), jobs.py (worker)
```
