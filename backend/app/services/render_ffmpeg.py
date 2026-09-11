# -*- coding: utf-8 -*-
"""Lightweight video render with ffmpeg only — no browser, no Node.

Each image gets an equal slice of the narration with a slow Ken Burns zoom; the
clips are concatenated, the narration is added, and the .srt captions are burned in.

Small hosts have little RAM, and libx264 + libass can be OOM-killed (exit -9) on a
dense/long video. So the render is **self-healing**: if a pass is killed, it retries
automatically at a lower resolution, and finally with a static (no-zoom) fallback,
so it always produces a video instead of failing. A bigger box / dedicated render
worker still gives the best quality — this just guarantees a result.
"""
import os, glob, shutil, subprocess, tempfile
from ..config import settings
from . import captions as captions_svc

import os as _os
FPS = 30
# 720p by default so it fits small instances; set FABULA_VIDEO_HEIGHT=1080 on a bigger box.
H = int(_os.environ.get("FABULA_VIDEO_HEIGHT", "720"))
W = (H * 16 // 9) // 2 * 2
# Supersample factor for the Ken Burns zoom. Only needs to cover the max zoom-in
# (~1.09), so a light 1.25x keeps it sharp without the memory cost of the old 2.5x.
UP_FACTOR = float(_os.environ.get("FABULA_RENDER_SUPERSAMPLE", "1.25"))
SUB_STYLE = ("FontName=DejaVu Serif,Fontsize=18,PrimaryColour=&H00FFFFFF&,"
             "OutlineColour=&H00201810&,BorderStyle=1,Outline=2,Shadow=0,"
             "Alignment=2,MarginV=48")


class _Killed(RuntimeError):
    """ffmpeg was killed by the OS (negative return code) — almost always OOM."""


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        tail = " | ".join(err.splitlines()[-10:]) if err else ""
        if r.returncode < 0:                     # SIGKILL/SIGSEGV → out of memory
            raise _Killed(f"ffmpeg killed (rc={r.returncode}): {tail}")
        raise RuntimeError(f"ffmpeg rc={r.returncode}: {tail}")


def _even(n):
    n = int(n)
    return max(160, n - (n % 2))


def _attempt(images_dir, audio_path, srt_path, out_path, log, W, H, kenburns):
    ff = settings.FFMPEG
    UP = _even(W * UP_FACTOR)
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    if not frames:
        raise RuntimeError(f"no images in {images_dir}")
    dur = captions_svc.audio_duration(audio_path)
    if not dur:
        raise RuntimeError("could not read narration duration")
    total = int(dur * FPS)
    n = len(frames)
    base = total // n

    work = tempfile.mkdtemp(prefix="fabula_render_")
    try:
        clips = []
        for i, img in enumerate(frames):
            d = total - base * (n - 1) if i == n - 1 else base   # last takes remainder
            d = max(2, d)
            clip = os.path.join(work, f"clip_{i:03d}.mp4")
            if kenburns:
                vf = (f"scale={UP}:-2,zoompan=z='min(zoom+0.00022,1.09)':"
                      f"d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                      "format=yuv420p")
            else:  # static, lightest possible — cover-fit the frame, no zoom
                vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                      f"crop={W}:{H},format=yuv420p")
            _run([ff, "-y", "-loglevel", "error", "-threads", "1", "-loop", "1", "-i", img,
                  "-vf", vf, "-frames:v", str(d), "-r", str(FPS),
                  "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                  "-x264-params", "rc-lookahead=1:ref=1:bframes=0:sync-lookahead=0",
                  "-pix_fmt", "yuv420p", clip])
            clips.append(clip)
        log(f"built {len(clips)} scene clips ({W}x{H}); joining + audio + captions")

        listf = os.path.join(work, "list.txt")
        with open(listf, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c.replace(os.sep, '/')}'\n")
        silent = os.path.join(work, "silent.mp4")
        _run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", listf, "-c", "copy", silent])

        # burn subtitles (relative path, cwd=work → avoids Windows drive-colon escaping)
        final = os.path.join(work, "final.mp4")
        cmd = [ff, "-y", "-loglevel", "error", "-threads", "1", "-i", silent, "-i", audio_path]
        has_subs = os.path.exists(srt_path) and os.path.getsize(srt_path) > 8
        if has_subs:
            shutil.copyfile(srt_path, os.path.join(work, "subs.srt"))
            cmd += ["-vf", f"subtitles=subs.srt:force_style='{SUB_STYLE}'"]
        else:
            log("no captions to burn — rendering without subtitles")
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-x264-params", "rc-lookahead=1:ref=1:bframes=0:sync-lookahead=0",
                "-c:a", "aac", "-b:a", "160k", "-shortest",
                "-map", "0:v:0", "-map", "1:a:0", final]
        _run(cmd, cwd=work)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.copyfile(final, out_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size_mb = os.path.getsize(out_path) / 1e6
    log(f"video rendered: {size_mb:.1f} MB @ {W}x{H} -> {os.path.basename(out_path)}")
    return out_path


def render_video(images_dir, audio_path, srt_path, out_path, log=lambda m: None, size=None):
    """Render, retrying at progressively lower resolution if the box runs out of memory."""
    W0, H0 = size if size else (globals()["W"], globals()["H"])
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    dur = captions_svc.audio_duration(audio_path) or 0
    log(f"ffmpeg render: {len(frames)} images over {dur:.0f}s (Ken Burns + burned captions)")

    # Ladder of attempts: full → 70% → 50% (all Ken Burns), then a static 50% last resort.
    plans = []
    for s in (1.0, 0.7, 0.5):
        plans.append((_even(W0 * s), _even(H0 * s), True))
    plans.append((_even(W0 * 0.5), _even(H0 * 0.5), False))

    last = None
    for i, (w, h, kb) in enumerate(plans):
        if i > 0:
            why = "no zoom, " if not kb else ""
            log(f"↓ previous attempt ran out of memory — retrying lighter ({why}{w}x{h})")
        try:
            return _attempt(images_dir, audio_path, srt_path, out_path, log, w, h, kb)
        except _Killed as e:
            last = e
            continue
        # any non-OOM ffmpeg error propagates immediately (retrying smaller won't help)
    raise RuntimeError(f"render failed even at reduced quality (out of memory): {last}")
