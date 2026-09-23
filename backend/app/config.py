# -*- coding: utf-8 -*-
"""Settings, loaded from environment / .env. No secrets ever hardcoded."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # backend/


def _load_dotenv():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


class Settings:
    APP_NAME = "Fábula API"
    VERSION = "0.4.0-fal-locked-characters"
    # SQLite for local dev; swap DATABASE_URL to Postgres/Supabase in production.
    DB_PATH = os.environ.get("FABULA_DB", os.path.join(ROOT, "data", "fabula.db"))
    OUTPUT_DIR = os.environ.get("FABULA_OUTPUT", os.path.join(ROOT, "data", "output"))
    # The Remotion render project (reuses the proven cuentos-pilot renderer for now;
    # production would ship a dedicated render image). Node/ffmpeg on PATH by default.
    # 'ffmpeg' (light, hostable) or 'remotion' (Chrome, fancier, needs Node+Chrome).
    RENDER_ENGINE = os.environ.get("FABULA_RENDER_ENGINE", "ffmpeg")
    REMOTION_PROJECT = os.environ.get("FABULA_REMOTION", "C:/Users/eiman/Downloads/cuentos-pilot")
    NODE = os.environ.get("FABULA_NODE", "node")
    FFMPEG = os.environ.get("FABULA_FFMPEG", "ffmpeg")
    # Dedicated render worker (a 2nd Railway service). When RENDER_WORKER_URL is set the
    # heavy video render is dispatched there instead of running in this API process; the
    # API polls the worker and pulls the finished video from R2. Leave unset = render
    # locally (current behavior). RENDER_SECRET authenticates API<->worker calls.
    RENDER_WORKER_URL = os.environ.get("FABULA_RENDER_WORKER_URL", "").strip().rstrip("/")
    RENDER_SECRET = os.environ.get("FABULA_RENDER_SECRET", "").strip()
    # Whether THIS process is allowed to run the Remotion (Chrome) engine. Off unless the
    # render worker has Node+Chrome and the Remotion licence is in place.
    REMOTION_ENABLED = os.environ.get("FABULA_REMOTION_ENABLED", "").strip().lower() in ("1", "true", "yes")
    # The Remotion Node project (cinematic engine), shipped at backend/remotion.
    REMOTION_DIR = os.environ.get("FABULA_REMOTION_DIR", os.path.join(ROOT, "remotion"))
    NPX = os.environ.get("FABULA_NPX", "npx.cmd" if os.name == "nt" else "npx")
    NODE = os.environ.get("FABULA_NODE", "node")
    # fal.ai models (BYOK). Base text-to-image + the reference/edit model that locks
    # character identity across scenes. Env-overridable as fal renames models.
    FAL_IMAGE_MODEL = os.environ.get("FABULA_FAL_IMAGE_MODEL", "fal-ai/flux/dev")
    FAL_EDIT_MODEL = os.environ.get("FABULA_FAL_EDIT_MODEL", "fal-ai/nano-banana/edit")
    # AWS Lambda backend for Remotion (set on the render worker only). Assets are pulled
    # from R2 by presigned URL; AWS creds come from the standard AWS_* env vars.
    LAMBDA_FUNCTION = os.environ.get("REMOTION_LAMBDA_FUNCTION", "").strip()
    LAMBDA_SERVE_URL = os.environ.get("REMOTION_LAMBDA_SERVE_URL", "").strip()
    LAMBDA_REGION = os.environ.get("REMOTION_LAMBDA_REGION", "us-east-1").strip()
    # Fernet key for encrypting stored BYOK provider keys. Generated on first run
    # if absent (dev only); in production set FABULA_SECRET to a fixed value.
    SECRET = os.environ.get("FABULA_SECRET", "")
    # YouTube Data API key for channel analysis (optional at scaffold stage).
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    CORS_ORIGINS = os.environ.get("FABULA_CORS", "*").split(",")
    # Cloudflare R2 (durable storage for finished files). Inert until all are set.
    # .strip() guards against stray spaces/newlines pasted with the keys.
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()


settings = Settings()
