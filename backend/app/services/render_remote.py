# -*- coding: utf-8 -*-
"""Dispatch the heavy video render to the dedicated render worker and wait for it.

The API never renders in-process when a worker is configured: it makes sure the
reviewed assets (images/narration/captions) are in R2, asks the worker to render,
polls the worker's status (mirroring its log into the job), then pulls the finished
video back. The worker has the big RAM/CPU; the API stays responsive.

Local dev: if the worker shares this machine's OUTPUT_DIR, no R2 is needed — the
worker reads/writes the same folder and the poll/finalise still works.
"""
import os, time, shutil
import httpx
from ..config import settings
from .. import catalog
from . import storage

POLL_EVERY = 3.0
MAX_WAIT = 3 * 60 * 60          # 3h safety cap for very long videos


def _headers():
    return {"X-Render-Secret": settings.RENDER_SECRET}


def render_via_worker(project, images_dir, audio_path, srt_path, out_path, engine, log):
    pid = project["id"]
    rid = f"{pid}-{int(time.time())}"
    vw, vh = catalog.video_dims(project.get("format"), project.get("resolution"))

    # Make the inputs reachable by the worker.
    if storage.enabled():
        try:
            storage.upload_dir(pid, os.path.join(settings.OUTPUT_DIR, pid), log)
        except Exception as e:
            log(f"R2 upload before render failed: {str(e)[:120]}")
    else:
        log("no R2 configured — worker must share this machine's output folder")

    base = settings.RENDER_WORKER_URL
    backend = catalog.remotion_backend(project.get("remotion_backend"))
    payload = {"render_id": rid, "pid": pid, "engine": engine, "backend": backend,
               "video_w": vw, "video_h": vh}
    r = httpx.post(base + "/render", headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    log(f"render dispatched to the worker ({engine}) — this runs off the app so it can't stall it")

    seen = 0
    started = time.time()
    while True:
        time.sleep(POLL_EVERY)
        if time.time() - started > MAX_WAIT:
            raise RuntimeError("render timed out on the worker")
        try:
            s = httpx.get(f"{base}/status/{rid}", headers=_headers(), timeout=30).json()
        except Exception as e:
            log(f"  (waiting on worker… {str(e)[:60]})")
            continue
        for line in s.get("log", [])[seen:]:
            log("  [worker] " + line)
        seen = len(s.get("log", []))
        st = s.get("status")
        if st == "done":
            break
        if st == "error":
            raise RuntimeError("worker render failed: " + str(s.get("error"))[:200])

    # The worker already put the video in R2. DON'T copy it onto the API's small disk —
    # the download endpoints serve it straight from R2. (Copying a big video here is what
    # filled the volume: "No space left on device".)
    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        log("render complete — video ready")            # shared-folder local dev
    elif storage.enabled() and storage.exists(pid, "video.mp4"):
        log("render complete — video stored in R2, served on demand (not copied to the app disk)")
    else:
        raise RuntimeError("worker finished but the video is not in R2")
    return out_path
