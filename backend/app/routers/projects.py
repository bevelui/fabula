# -*- coding: utf-8 -*-
import json, os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from ..config import settings
from .. import db, catalog
from ..services import storage
from ..models import ProjectCreate
from ..deps import current_user
from ..services import jobs

router = APIRouter(tags=["projects"])


@router.post("/projects")
def create_project(body: ProjectCreate, user: str = Depends(current_user)):
    if not catalog.is_language_supported(body.language):
        raise HTTPException(400, f"language '{body.language}' is not available yet")
    src = "own" if body.script_source == "own" else "channel"
    if src == "channel" and not body.channel_url.strip():
        raise HTTPException(400, "add a channel URL, or switch to 'my own script'")
    if src == "own" and not (body.user_script or "").strip():
        raise HTTPException(400, "paste your script, or switch to 'learn from a channel'")
    mode = body.script_mode if body.script_mode in ("asis", "polish", "reference") else "asis"
    pid = db.new_id("proj")
    db.insert("projects", {
        "id": pid, "user_id": user,
        "title": body.title or "Untitled project",
        "channel_url": body.channel_url,
        "script_source": src, "user_script": body.user_script, "script_mode": mode,
        "format": "short" if body.format == "short" else "long",
        "language": body.language,
        "style_id": body.style_id, "style_custom": body.style_custom,
        "voice_id": body.voice_id,
        "image_provider": body.image_provider, "audio_provider": body.audio_provider,
        "script_model": catalog.llm_model(body.script_model, body.script_model_custom),
        "scene_model": catalog.llm_model(body.scene_model, body.scene_model_custom),
        "length_words": body.length_words, "num_images": body.num_images,
        "status": "draft",
        "created_at": db.now(), "updated_at": db.now(),
    })
    return db.fetchone("projects", id=pid)


@router.get("/projects")
def list_projects(user: str = Depends(current_user)):
    return db.fetchall("projects", user_id=user)


@router.get("/projects/{pid}")
def get_project(pid: str, user: str = Depends(current_user)):
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.post("/projects/{pid}/generate")
def generate(pid: str, user: str = Depends(current_user)):
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    jid = jobs.create_job(p)
    return {"job_id": jid, "status": "queued"}


@router.get("/projects/{pid}/file")
def project_file(pid: str, name: str, user: str = Depends(current_user)):
    """Download/preview an output file for a project (video.mp4, thumbnail.jpg, …)."""
    if not db.fetchone("projects", id=pid, user_id=user):
        raise HTTPException(404, "project not found")
    safe = os.path.basename(name)                       # prevent path traversal
    path = os.path.join(settings.OUTPUT_DIR, pid, safe)
    if os.path.isfile(path):
        return FileResponse(path, filename=safe)
    if storage.enabled():                               # durable copy in R2
        try:
            return RedirectResponse(storage.presigned_url(pid, safe))
        except Exception:
            pass
    raise HTTPException(404, "file not found")


@router.get("/projects/{pid}/zip")
def project_zip(pid: str, user: str = Depends(current_user)):
    """Download everything the project generated (script, audio, images, captions,
    video, thumbnail) as one zip."""
    if not db.fetchone("projects", id=pid, user_id=user):
        raise HTTPException(404, "project not found")
    folder = os.path.join(settings.OUTPUT_DIR, pid)
    if not os.path.isdir(folder) or not os.listdir(folder):
        raise HTTPException(404, "nothing generated yet")
    import zipfile, tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, folder))
    return FileResponse(tmp.name, filename=f"fabula-{pid}.zip",
                        media_type="application/zip")


@router.get("/jobs/{jid}")
def get_job(jid: str, user: str = Depends(current_user)):
    j = db.fetchone("jobs", id=jid, user_id=user)
    if not j:
        raise HTTPException(404, "job not found")
    j["log"] = json.loads(j.get("log") or "[]")
    j["artifacts"] = json.loads(j.get("artifacts") or "{}")
    return j
