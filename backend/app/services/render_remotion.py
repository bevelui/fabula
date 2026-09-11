# -*- coding: utf-8 -*-
"""Cinematic (Remotion) render via the Node CLI — the no-AWS path for solo/dev use.

Stages the reviewed artifacts (images + narration + word-level captions.json) into a
temp public dir, writes props.json, and runs `npx remotion render` against the
fabula/remotion project. It is the SAME composition that deploys to AWS Lambda at
launch, so this work is reused as-is. Enable with FABULA_REMOTION_ENABLED=1 on an
environment that has Node + a headless browser (the render worker image).
"""
import os, json, glob, shutil, tempfile, subprocess
from ..config import settings


def _load_caps(caps_json):
    try:
        raw = json.load(open(caps_json, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for c in raw:
        out.append({"text": c.get("text", ""),
                    "startMs": int(c.get("startMs", c.get("start", 0))),
                    "endMs": int(c.get("endMs", c.get("end", 0)))})
    return out


def render_video(images_dir, audio_path, captions_json, out_path, size, fps=30,
                 log=lambda m: None, accent="#E6A23C"):
    rdir = settings.REMOTION_DIR
    if not os.path.isdir(os.path.join(rdir, "src")):
        raise RuntimeError(f"Remotion project not found at {rdir} (set FABULA_REMOTION_DIR)")
    w, h = size
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    if not frames:
        raise RuntimeError("no images to render")

    work = tempfile.mkdtemp(prefix="fabula_remotion_")
    pub = os.path.join(work, "public", "assets")
    os.makedirs(pub, exist_ok=True)
    try:
        names = []
        for i, src in enumerate(frames, 1):
            shutil.copyfile(src, os.path.join(pub, f"img-{i:03d}.jpg"))
            names.append(f"assets/img-{i:03d}.jpg")
        shutil.copyfile(audio_path, os.path.join(pub, "narration.mp3"))
        props = {"images": names, "audioSrc": "assets/narration.mp3",
                 "captions": _load_caps(captions_json) if captions_json else [],
                 "fps": fps, "width": w, "height": h, "accent": accent}
        propf = os.path.join(work, "props.json")
        with open(propf, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False)
        log(f"cinematic (Remotion): {len(names)} images, {len(props['captions'])} caption words, {w}x{h}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        cmd = [settings.NPX, "remotion", "render", "src/index.ts", "Story", out_path,
               f"--props={propf}", f"--public-dir={os.path.join(work, 'public')}", "--log=error"]
        r = subprocess.run(cmd, cwd=rdir, capture_output=True, text=True)
        if r.returncode != 0:
            tail = " | ".join((r.stderr or "").strip().splitlines()[-12:])
            raise RuntimeError(f"remotion render failed rc={r.returncode}: {tail[:400]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not (os.path.isfile(out_path) and os.path.getsize(out_path) > 0):
        raise RuntimeError("remotion produced no output file")
    log(f"cinematic render done: {os.path.getsize(out_path)/1e6:.1f} MB -> {os.path.basename(out_path)}")
    return out_path
