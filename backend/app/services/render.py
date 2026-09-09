# -*- coding: utf-8 -*-
"""Video render — stitches images + narration + captions into an mp4 via the proven
Remotion project (cuentos-pilot's render-video.mjs: muted frame render + ffmpeg mux).

This is the heavy stage. It stages the project's assets into the Remotion project's
public/ folder, writes scenes.ts, runs the render, and copies out the mp4. One render
at a time (matches the in-process worker); production swaps this for a queue of
dedicated render workers, but the staging + command are identical.
"""
import os, glob, shutil, subprocess
from ..config import settings


def render_video(images_dir, audio_path, captions_json, out_path, log=lambda m: None):
    proj = settings.REMOTION_PROJECT
    if not os.path.isdir(proj):
        raise RuntimeError(f"Remotion project not found: {proj}")
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    if not frames:
        raise RuntimeError(f"no images in {images_dir}")

    pub = os.path.join(proj, "public")
    story = os.path.join(pub, "story")
    if os.path.isdir(story):
        shutil.rmtree(story)
    os.makedirs(story, exist_ok=True)

    scene_rel = []
    for src in frames:
        name = os.path.basename(src)
        shutil.copyfile(src, os.path.join(story, name))
        scene_rel.append(f"story/{name}")
    shutil.copyfile(audio_path, os.path.join(pub, "narration.mp3"))
    shutil.copyfile(captions_json, os.path.join(pub, "captions.json"))

    scenes_ts = os.path.join(proj, "src", "Story", "scenes.ts")
    with open(scenes_ts, "w", encoding="utf-8") as f:
        f.write("export const SCENES: string[] = [\n")
        for s in scene_rel:
            f.write(f'  "{s}",\n')
        f.write("];\n")
    log(f"staged {len(scene_rel)} frames + audio + captions; rendering (Remotion)…")

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([settings.NODE, "render-video.mjs"], cwd=proj, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        log("render failed:\n  " + "\n  ".join(tail))
        raise RuntimeError("Remotion render failed")

    produced = os.path.join(proj, "out", "story.mp4")
    if not os.path.exists(produced):
        raise RuntimeError("render finished but out/story.mp4 is missing")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    shutil.copyfile(produced, out_path)
    size_mb = os.path.getsize(out_path) / 1e6
    log(f"video rendered: {size_mb:.1f} MB -> {os.path.basename(out_path)}")
    return out_path
