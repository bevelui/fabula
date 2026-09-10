# -*- coding: utf-8 -*-
"""Fábula API — the cloud engine behind the app. FastAPI entrypoint."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .config import settings
from . import db
from .routers import catalog, projects, keys, feedback

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "app": settings.APP_NAME, "version": settings.VERSION}


@app.get("/", include_in_schema=False)
def home():
    index = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"name": settings.APP_NAME, "docs": "/docs"}


@app.get("/api", tags=["meta"])
def api_info():
    """Diagnostics — confirms whether the DB (keys+projects) is on persistent storage."""
    from .services import storage
    dbp = settings.DB_PATH
    info = {
        "name": settings.APP_NAME, "version": settings.VERSION, "docs": "/docs",
        "db_path": dbp,
        "db_exists": os.path.exists(dbp),
        "db_size_bytes": os.path.getsize(dbp) if os.path.exists(dbp) else 0,
        "output_dir": settings.OUTPUT_DIR,
        "r2_enabled": storage.enabled(),
    }
    try:
        info["projects_in_db"] = len(db.fetchall("projects"))
        info["keys_in_db"] = len(db.fetchall("provider_keys"))
    except Exception as e:
        info["db_error"] = str(e)[:150]
    return info


app.include_router(catalog.router)
app.include_router(projects.router)
app.include_router(keys.router)
app.include_router(feedback.router)
