# -*- coding: utf-8 -*-
"""Cinematic (Remotion) render on AWS Lambda — the fast, parallel, scalable backend.

Runs on the render worker (which has Node + the Remotion project). Assets are handed
to Lambda by presigned R2 URL (Lambda renders in the cloud, so it can't read local
files); a small Node script (remotion/lambda-render.mjs) does the actual dispatch via
the official @remotion/lambda SDK, polls progress, and downloads the finished video.

Requires REMOTION_LAMBDA_FUNCTION + REMOTION_LAMBDA_SERVE_URL (from the one-time AWS
deploy) and AWS creds in the standard AWS_* env vars, plus R2 for the assets.
"""
import os, json, glob, shutil, tempfile, subprocess
from ..config import settings
from . import storage, render_remotion


def render(pid, images_dir, out_path, size, fps=30, log=lambda m: None, accent="#E6A23C"):
    if not (settings.LAMBDA_FUNCTION and settings.LAMBDA_SERVE_URL):
        raise RuntimeError("lambda backend not configured (REMOTION_LAMBDA_FUNCTION / _SERVE_URL)")
    if not storage.enabled():
        raise RuntimeError("lambda backend needs R2 (assets are pulled by URL)")
    w, h = size
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    if not frames:
        raise RuntimeError("no images to render")
    images = [storage.presigned_url(pid, f"images/{os.path.basename(f)}", expires=6 * 3600)
              for f in frames]
    audio = storage.presigned_url(pid, "narration.mp3", expires=6 * 3600)
    caps = render_remotion._load_caps(os.path.join(os.path.dirname(images_dir), "captions.json"))
    props = {"images": images, "audioSrc": audio, "captions": caps,
             "fps": fps, "width": w, "height": h, "accent": accent}

    work = tempfile.mkdtemp(prefix="fabula_lambda_")
    try:
        propf = os.path.join(work, "props.json")
        with open(propf, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        log(f"cinematic (Lambda): dispatching {len(images)} images @ {w}x{h} to AWS…")
        script = os.path.join(settings.REMOTION_DIR, "lambda-render.mjs")
        r = subprocess.run(
            [settings.NODE, script, propf, out_path,
             settings.LAMBDA_FUNCTION, settings.LAMBDA_REGION, settings.LAMBDA_SERVE_URL],
            cwd=settings.REMOTION_DIR, capture_output=True, text=True)
        for line in (r.stderr or "").strip().splitlines()[-15:]:
            log("  [lambda] " + line)
        if r.returncode != 0:
            raise RuntimeError(f"lambda render failed rc={r.returncode}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not (os.path.isfile(out_path) and os.path.getsize(out_path) > 0):
        raise RuntimeError("lambda produced no output file")
    log(f"cinematic (Lambda) done: {os.path.getsize(out_path)/1e6:.1f} MB")
    return out_path
