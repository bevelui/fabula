# -*- coding: utf-8 -*-
import json, os, glob
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from ..config import settings
from .. import db, catalog
from ..services import storage, image_gen
from typing import Optional
from ..models import ProjectCreate, RegenImage, ApproveBody
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
    fmt_id = "short" if body.format == "short" else "long"
    res = catalog.resolution(body.resolution) if body.resolution else catalog.default_resolution(fmt_id)
    pid = db.new_id("proj")
    db.insert("projects", {
        "id": pid, "user_id": user,
        "title": body.title or "Untitled project",
        "channel_url": body.channel_url,
        "script_source": src, "user_script": body.user_script, "script_mode": mode,
        "format": fmt_id,
        "language": body.language,
        "style_id": body.style_id, "style_custom": body.style_custom,
        "voice_id": body.voice_id,
        "image_provider": body.image_provider, "audio_provider": body.audio_provider,
        "script_model": catalog.llm_model(body.script_model, body.script_model_custom),
        "scene_model": catalog.llm_model(body.scene_model, body.scene_model_custom),
        "length_words": body.length_words, "num_images": body.num_images,
        "render_engine": catalog.render_engine(body.render_engine),
        "remotion_backend": catalog.remotion_backend(body.remotion_backend),
        "resolution": res,
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


def _last_prepare_artifacts(project):
    """Artifacts of the project's most recent job (script/audio/images/scene_prompts)."""
    last = project.get("last_job_id")
    j = db.fetchone("jobs", id=last) if last else None
    return json.loads(j.get("artifacts") or "{}") if j else {}


def _images_dir(pid):
    return os.path.join(settings.OUTPUT_DIR, pid, "images")


@router.post("/projects/{pid}/generate")
def generate(pid: str, fresh: bool = False, user: str = Depends(current_user)):
    """Step 1 (prepare): script -> narration -> prompts -> images, then pause at REVIEW.
    Resumes by default (skips finished stages); fresh=1 regenerates everything."""
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    jid = jobs.create_job(p, phase="prepare", fresh=fresh)
    return {"job_id": jid, "status": "queued", "phase": "prepare", "fresh": fresh}


@router.post("/projects/{pid}/approve")
def approve(pid: str, body: Optional[ApproveBody] = None, user: str = Depends(current_user)):
    """Step 2 (assemble): user approved the images -> captions -> render -> thumbnail.
    An optional {engine} picks the render engine (ffmpeg | remotion) for this render."""
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    art = _last_prepare_artifacts(p)
    if not art.get("audio"):
        raise HTTPException(400, "no narration yet — run and review step 1 first")
    have = sorted(glob.glob(os.path.join(_images_dir(pid), "img-*.jpg")))
    if not have:
        raise HTTPException(400, "no images to render — regenerate at least one, then approve")
    upd = {}
    if body and body.engine:
        upd["render_engine"] = catalog.render_engine(body.engine)
    if body and body.backend:
        upd["remotion_backend"] = catalog.remotion_backend(body.backend)
    if body and body.resolution:
        upd["resolution"] = catalog.resolution(body.resolution)
    if upd:
        db.update("projects", pid, upd)
        p.update(upd)
    jid = jobs.create_job(p, phase="assemble")
    return {"job_id": jid, "status": "queued", "phase": "assemble",
            "engine": p.get("render_engine", "ffmpeg"),
            "backend": catalog.remotion_backend(p.get("remotion_backend")),
            "resolution": catalog.resolution(p.get("resolution"))}


@router.get("/projects/{pid}/images")
def list_images(pid: str, user: str = Depends(current_user)):
    """The review gallery: one entry per image with its scene prompt and a viewable URL."""
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    art = _last_prepare_artifacts(p)
    prompts = art.get("scene_prompts") or []
    frames = sorted(glob.glob(os.path.join(_images_dir(pid), "img-*.jpg")))
    idxs = sorted({int(os.path.basename(f)[4:7]) for f in frames}
                  | set(range(1, len(prompts) + 1)))
    out = []
    for i in idxs:
        on_disk = os.path.isfile(os.path.join(_images_dir(pid), f"img-{i:03d}.jpg"))
        out.append({
            "index": i,
            "url": f"/projects/{pid}/image/{i}?uid={user}",
            "prompt": prompts[i - 1] if i - 1 < len(prompts) else "",
            "ready": on_disk,
        })
    return {"format": p.get("format"), "resolution": catalog.resolution(p.get("resolution")),
            "engine": catalog.render_engine(p.get("render_engine")),
            "backend": catalog.remotion_backend(p.get("remotion_backend")),
            "count": len(out), "images": out}


@router.get("/projects/{pid}/image/{n}")
def get_image(pid: str, n: int, user: str = Depends(current_user)):
    """Serve one image (local volume first, R2 presigned fallback)."""
    if not db.fetchone("projects", id=pid, user_id=user):
        raise HTTPException(404, "project not found")
    name = f"img-{int(n):03d}.jpg"
    path = os.path.join(_images_dir(pid), name)
    if os.path.isfile(path):
        return FileResponse(path, media_type="image/jpeg")
    if storage.enabled():
        try:
            return RedirectResponse(storage.presigned_url(pid, f"images/{name}"))
        except Exception:
            pass
    raise HTTPException(404, "image not found")


@router.post("/projects/{pid}/regenerate-image")
def regenerate_image(pid: str, body: RegenImage, user: str = Depends(current_user)):
    """Redo one image in place — reuse its scene prompt, or an edited prompt from the user."""
    p = db.fetchone("projects", id=pid, user_id=user)
    if not p:
        raise HTTPException(404, "project not found")
    art = _last_prepare_artifacts(p)
    prompts = art.get("scene_prompts") or []
    idx = body.index
    prompt = (body.prompt or "").strip() or (prompts[idx - 1] if idx - 1 < len(prompts) else "")
    if not prompt:
        raise HTTPException(400, "no prompt for that image — run step 1 first, or supply a prompt")
    prov = catalog.image_provider(p.get("image_provider") or "pollinations")
    need = prov["key"]
    keys = jobs._load_keys(user)
    if need and not keys.get(need):
        raise HTTPException(400, f"'{prov['name']}' needs your {need} key, or switch to the free engine")
    dims = catalog.fmt(p.get("format")).get("img", (1536, 864))
    out = os.path.join(_images_dir(pid), f"img-{idx:03d}.jpg")
    logs = []
    try:
        image_gen.generate_one(prov["id"], prompt, out, keys, size=dims, log=logs.append)
    except Exception as e:
        raise HTTPException(502, f"image engine failed: {str(e)[:160]}")
    # persist an edited prompt back into the reviewed artifacts so a re-render/prompts.txt agree
    if body.prompt and idx - 1 < len(prompts):
        prompts[idx - 1] = prompt
        last = p.get("last_job_id")
        j = db.fetchone("jobs", id=last) if last else None
        if j:
            a = json.loads(j.get("artifacts") or "{}")
            a["scene_prompts"] = prompts
            db.update("jobs", last, {"artifacts": json.dumps(a)})
    if storage.enabled():
        try:
            storage.upload_one(pid, out, f"images/img-{idx:03d}.jpg")
        except Exception:
            pass
    return {"ok": True, "index": idx,
            "url": f"/projects/{pid}/image/{idx}?uid={user}", "prompt": prompt}


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
