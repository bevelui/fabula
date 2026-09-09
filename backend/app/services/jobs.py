# -*- coding: utf-8 -*-
"""In-process background job worker.

MVP-simple: each job runs in a daemon thread, stepping through engine.STAGES and
persisting status/progress/log to the DB so the app can poll /jobs/{id}. In
production this becomes a real queue (Redis + RQ/Celery) with separate render
workers — the DB shape and the /jobs API stay the same.
"""
import json, threading, traceback
from .. import db, security
from . import engine


def _load_keys(user_id):
    """Decrypt this user's BYOK provider keys into {provider: plaintext} in-memory."""
    keys = {}
    for row in db.fetchall("provider_keys", user_id=user_id):
        try:
            keys[row["provider"]] = security.decrypt(row["ciphertext"])
        except Exception:
            pass
    return keys


def create_job(project):
    jid = db.new_id("job")
    db.insert("jobs", {
        "id": jid, "project_id": project["id"], "user_id": project["user_id"],
        "status": "queued", "stage": None, "progress": 0.0,
        "log": "[]", "error": None, "artifacts": "{}",
        "created_at": db.now(), "updated_at": db.now(),
    })
    db.update("projects", project["id"], {"status": "running"})
    threading.Thread(target=_run, args=(jid,), daemon=True).start()
    return jid


def _run(jid):
    job = db.fetchone("jobs", id=jid)
    project = db.fetchone("projects", id=job["project_id"])
    keys = _load_keys(job["user_id"])
    lines, artifacts = [], {}

    def log(msg):
        lines.append(msg)
        db.update("jobs", jid, {"log": json.dumps(lines)})

    try:
        db.update("jobs", jid, {"status": "running"})
        n = len(engine.STAGES)
        for i, (key, label) in enumerate(engine.STAGES):
            db.update("jobs", jid, {"stage": label, "progress": round(i / n, 3)})
            log(f"=== {label} ===")
            artifacts.update(engine.run_stage(key, project, log, keys, artifacts))
            db.update("jobs", jid, {"artifacts": json.dumps(artifacts)})
        db.update("jobs", jid, {"status": "done", "stage": "complete", "progress": 1.0})
        db.update("projects", project["id"], {"status": "done"})
        log("JOB COMPLETE")
    except Exception as e:
        db.update("jobs", jid, {"status": "error", "error": str(e)})
        db.update("projects", project["id"], {"status": "error"})
        log("JOB FAILED: " + str(e))
        traceback.print_exc()
