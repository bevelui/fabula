# -*- coding: utf-8 -*-
"""In-process background job worker, phase-aware and resumable.

  phase 'prepare'  -> analyze, script, audio, images  -> ends at status 'review'
  phase 'assemble' -> captions, video, thumbnail       -> ends at status 'done'
  phase 'full'     -> everything in one go (legacy)

RESUME: a new job is seeded with the previous job's artifacts, and any stage whose
output already exists on disk is skipped ("reused") instead of re-run. So a render
that failed does NOT regenerate the script/voice/images — it picks up where it left
off. Pass fresh=True to force everything to regenerate from scratch.

If only the render (assemble) fails, the project drops back to 'review' rather than
'error', so the user can simply approve again to retry (now reusing the images).
"""
import os, glob, json, threading, traceback
from .. import db, security
from ..config import settings
from . import engine, storage

PREPARE = ["analyze", "script", "audio", "images"]
ASSEMBLE = ["captions", "video", "thumbnail"]
_LABELS = dict(engine.STAGES)


def _load_keys(user_id):
    keys = {}
    for row in db.fetchall("provider_keys", user_id=user_id):
        try:
            keys[row["provider"]] = security.decrypt(row["ciphertext"])
        except Exception:
            pass
    return keys


def _stage_keys(phase):
    if phase == "prepare":
        return PREPARE
    if phase == "assemble":
        return ASSEMBLE
    return [k for k, _ in engine.STAGES]


def _out(project):
    return os.path.join(settings.OUTPUT_DIR, project["id"])


def _isfile(p):
    return bool(p) and os.path.isfile(p) and os.path.getsize(p) > 0


def _stage_done(key, project, art):
    """True when this stage's output already exists and can be reused."""
    d = _out(project)
    if key == "analyze":
        return "style_profile" in art
    if key == "script":
        return bool(art.get("script")) and _isfile(os.path.join(d, "script.txt"))
    if key == "audio":
        return bool(art.get("audio")) and _isfile(os.path.join(d, "narration.mp3"))
    if key == "images":
        got = len(glob.glob(os.path.join(d, "images", "img-*.jpg")))
        return bool(art.get("images")) and got > 0 and got >= int(art.get("image_count") or 1)
    if key == "captions":
        return bool(art.get("srt")) and _isfile(art.get("srt"))
    if key == "video":
        return _isfile(os.path.join(d, "video.mp4"))
    if key == "thumbnail":
        return _isfile(os.path.join(d, "thumbnail.jpg"))
    return False


def _has_prepare(project, art):
    return _stage_done("audio", project, art) and _stage_done("images", project, art)


def create_job(project, phase="prepare", fresh=False):
    jid = db.new_id("job")
    seed = {}
    # assemble always needs the prepared artifacts; prepare/full reuse them unless fresh
    if phase == "assemble" or not fresh:
        last = project.get("last_job_id")
        pj = db.fetchone("jobs", id=last) if last else None
        if pj:
            seed = json.loads(pj.get("artifacts") or "{}")
    db.insert("jobs", {
        "id": jid, "project_id": project["id"], "user_id": project["user_id"],
        "status": "queued", "stage": None, "progress": 0.0,
        "log": "[]", "error": None, "artifacts": json.dumps(seed),
        "phase": phase, "created_at": db.now(), "updated_at": db.now(),
    })
    db.update("projects", project["id"], {"status": "running", "last_job_id": jid})
    threading.Thread(target=_run, args=(jid,), daemon=True).start()
    return jid


def _run(jid):
    job = db.fetchone("jobs", id=jid)
    project = db.fetchone("projects", id=job["project_id"])
    keys = _load_keys(job["user_id"])
    phase = job.get("phase") or "full"
    stage_keys = _stage_keys(phase)
    lines = []
    artifacts = json.loads(job.get("artifacts") or "{}")

    def log(msg):
        lines.append(msg)
        db.update("jobs", jid, {"log": json.dumps(lines)})

    try:
        db.update("jobs", jid, {"status": "running"})
        n = len(stage_keys)
        for i, key in enumerate(stage_keys):
            label = _LABELS.get(key, key)
            db.update("jobs", jid, {"stage": label, "progress": round(i / n, 3)})
            log(f"=== {label} ===")
            if _stage_done(key, project, artifacts):
                log(f"✓ reusing {label.lower()} from the earlier run (skipped)")
                continue
            artifacts.update(engine.run_stage(key, project, log, keys, artifacts))
            db.update("jobs", jid, {"artifacts": json.dumps(artifacts)})
        end = "review" if phase == "prepare" else "done"
        db.update("jobs", jid, {"status": end, "stage": "complete", "progress": 1.0})
        db.update("projects", project["id"], {"status": end})
        log("READY TO REVIEW — check the images, then Approve to render"
            if phase == "prepare" else "JOB COMPLETE")
        if storage.enabled():
            try:
                storage.upload_dir(project["id"], _out(project), log)
            except Exception as e:
                log(f"R2 upload skipped: {str(e)[:120]}")
    except Exception as e:
        # If the prepared assets survive (only the render failed), fall back to REVIEW
        # so the user can just approve again to retry — not a dead 'error' state.
        recoverable = phase != "prepare" and _has_prepare(project, artifacts)
        end = "review" if recoverable else "error"
        db.update("jobs", jid, {"status": end, "error": str(e)})
        db.update("projects", project["id"], {"status": end})
        if recoverable:
            log("RENDER FAILED: " + str(e)[:200])
            log("Your script, voice and images are safe. Click Approve to retry the "
                "render (it will reuse them and step down quality if memory is tight).")
        else:
            log("JOB FAILED: " + str(e))
        traceback.print_exc()
