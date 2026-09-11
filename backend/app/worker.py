# -*- coding: utf-8 -*-
"""Fábula render worker — a second service that does ONLY the heavy video render.

Same repo/image as the API; deploy it as a separate Railway service whose start
command is `uvicorn app.worker:app`. It pulls the reviewed assets from R2 (or reads
a shared folder in local dev), renders with the chosen engine, uploads the finished
video back to R2, and reports progress over /status. All calls are guarded by a shared
secret (FABULA_RENDER_SECRET) that must match the API's.

Keeping rendering here means the API never runs libx264/Chrome in its own process, so
a 30–60 min render can't stall the app, and the worker can be sized (RAM/CPU/disk)
independently of the user-facing service.
"""
import os, glob, time, threading, traceback
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from .config import settings
from .services import storage, render_ffmpeg, render_remotion, render_lambda

app = FastAPI(title="Fábula Render Worker", version=settings.VERSION)

# render_id -> {status, progress, log[], error}
_RENDERS = {}


class RenderReq(BaseModel):
    render_id: str
    pid: str
    engine: str = "ffmpeg"
    backend: str = "worker"          # remotion backend: 'worker' (Chrome) | 'lambda' (AWS)
    video_w: int = 1280
    video_h: int = 720


def _auth(secret):
    if not settings.RENDER_SECRET:
        raise HTTPException(503, "worker has no FABULA_RENDER_SECRET set")
    if secret != settings.RENDER_SECRET:
        raise HTTPException(401, "bad render secret")


def _ensure(pid, name, dest, log):
    """Make sure an input file is present locally (shared folder), else pull from R2."""
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return True
    return storage.download_one(pid, name, dest, log)


def _render_cinematic(pid, images, audio, caps_json, srt, out, w, h, backend, log, tries=3):
    """Render Remotion (worker/Chrome or AWS Lambda) with up to `tries` attempts, then
    fall back to the standard ffmpeg engine so a video is always produced."""
    use_lambda = (backend == "lambda" and settings.LAMBDA_FUNCTION
                  and settings.LAMBDA_SERVE_URL and storage.enabled())
    if backend == "lambda" and not use_lambda:
        log("Lambda backend isn't configured on this worker — using the built-in worker (Chrome)")
    label = "Lambda" if use_lambda else "worker/Chrome"
    for attempt in range(1, tries + 1):
        try:
            if use_lambda:
                render_lambda.render(pid, images, out, size=(w, h), log=log)
            else:
                render_remotion.render_video(images, audio, caps_json, out, size=(w, h), log=log)
            return "remotion"
        except Exception as e:
            log(f"cinematic ({label}) attempt {attempt}/{tries} failed: {str(e)[:160]}")
            if attempt < tries:
                time.sleep(2 * attempt)
    log(f"cinematic engine failed after {tries} tries — falling back to the standard "
        "(ffmpeg) engine so you still get a video")
    render_ffmpeg.render_video(images, audio, srt, out, log, size=(w, h))
    return "ffmpeg"


def _do_render(req: RenderReq):
    rec = _RENDERS[req.render_id]
    log = lambda m: rec["log"].append(m)
    pid = req.pid
    try:
        outdir = os.path.join(settings.OUTPUT_DIR, pid)
        images = os.path.join(outdir, "images")
        audio = os.path.join(outdir, "narration.mp3")
        srt = os.path.join(outdir, "video.srt")
        caps_json = os.path.join(outdir, "captions.json")
        out = os.path.join(outdir, "video.mp4")

        rec["status"] = "running"
        # gather inputs (local-first, then R2)
        if not glob.glob(os.path.join(images, "img-*.jpg")):
            storage.download_prefix(pid, "images/", images, log)
        _ensure(pid, "narration.mp3", audio, log)
        _ensure(pid, "video.srt", srt, log)          # captions (ffmpeg) — optional
        _ensure(pid, "captions.json", caps_json, log)  # captions (remotion) — optional
        if not glob.glob(os.path.join(images, "img-*.jpg")):
            raise RuntimeError("no images available to render")
        if not (os.path.isfile(audio) and os.path.getsize(audio) > 0):
            raise RuntimeError("no narration available to render")

        engine = req.engine
        if engine == "remotion" and not settings.REMOTION_ENABLED:
            log("Remotion isn't enabled on this worker yet (needs Node+Chrome + licence) "
                "— rendering with ffmpeg instead so you still get a video")
            engine = "ffmpeg"

        if engine == "remotion":
            rec["engine_used"] = _render_cinematic(pid, images, audio, caps_json, srt, out,
                                                   req.video_w, req.video_h, req.backend, log)
        else:
            render_ffmpeg.render_video(images, audio, srt, out, log, size=(req.video_w, req.video_h))

        if storage.enabled():
            try:
                storage.upload_one(pid, out, "video.mp4", log)
            except Exception as e:
                log(f"R2 upload of video failed: {str(e)[:120]}")
        rec["status"] = "done"
        rec["progress"] = 1.0
        log("worker render finished")
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = str(e)
        log("render failed: " + str(e)[:200])
        traceback.print_exc()


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "role": "render-worker", "version": settings.VERSION,
            "remotion": settings.REMOTION_ENABLED, "r2": storage.enabled(),
            "active": sum(1 for r in _RENDERS.values() if r["status"] in ("queued", "running"))}


@app.post("/render")
def render(req: RenderReq, x_render_secret: str = Header(None)):
    _auth(x_render_secret)
    _RENDERS[req.render_id] = {"status": "queued", "progress": 0.0, "log": [], "error": None}
    threading.Thread(target=_do_render, args=(req,), daemon=True).start()
    return {"accepted": True, "render_id": req.render_id}


@app.get("/status/{rid}")
def status(rid: str, x_render_secret: str = Header(None)):
    _auth(x_render_secret)
    rec = _RENDERS.get(rid)
    if not rec:
        raise HTTPException(404, "unknown render id")
    return rec
