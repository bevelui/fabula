# -*- coding: utf-8 -*-
"""Lightweight video render with ffmpeg only — no browser, no Node.

Each image gets an equal slice of the narration with a slow Ken Burns zoom; the
clips are concatenated, the narration is added, and the .srt captions are burned in.
Far lighter than Remotion (one dependency, modest RAM) so it hosts cheaply.
"""
import os, glob, shutil, subprocess, tempfile
from ..config import settings
from . import captions as captions_svc

import os as _os
FPS = 30
# 720p by default so it fits small instances; set FABULA_VIDEO_HEIGHT=1080 on a bigger box.
H = int(_os.environ.get("FABULA_VIDEO_HEIGHT", "720"))
W = (H * 16 // 9) // 2 * 2
_UP = (W * 5 // 2) // 2 * 2                       # 2.5x supersample (memory-safe on small box)
SUB_STYLE = ("FontName=DejaVu Serif,Fontsize=18,PrimaryColour=&H00FFFFFF&,"
             "OutlineColour=&H00201810&,BorderStyle=1,Outline=2,Shadow=0,"
             "Alignment=2,MarginV=48")


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        tail = " | ".join(err.splitlines()[-10:]) if err else ""
        killed = r.returncode < 0
        note = " [process killed — out of memory; try a shorter video or more RAM]" if killed else ""
        raise RuntimeError(f"ffmpeg rc={r.returncode}{note}: {tail}")


def render_video(images_dir, audio_path, srt_path, out_path, log=lambda m: None):
    ff = settings.FFMPEG
    frames = sorted(glob.glob(os.path.join(images_dir, "img-*.jpg")))
    if not frames:
        raise RuntimeError(f"no images in {images_dir}")
    dur = captions_svc.audio_duration(audio_path)
    if not dur:
        raise RuntimeError("could not read narration duration")
    total = int(dur * FPS)
    n = len(frames)
    base = total // n
    log(f"ffmpeg render: {n} images over {dur:.0f}s (Ken Burns + burned captions)")

    work = tempfile.mkdtemp(prefix="fabula_render_")
    try:
        clips = []
        for i, img in enumerate(frames):
            d = total - base * (n - 1) if i == n - 1 else base   # last takes remainder
            d = max(2, d)
            clip = os.path.join(work, f"clip_{i:03d}.mp4")
            # light upscale + gentle zoom; ultrafast = lowest memory
            zoom = (f"scale={_UP}:-2,zoompan=z='min(zoom+0.00022,1.09)':"
                    f"d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                    "format=yuv420p")
            _run([ff, "-y", "-loglevel", "error", "-threads", "1", "-loop", "1", "-i", img,
                  "-vf", zoom, "-frames:v", str(d), "-r", str(FPS),
                  "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                  "-pix_fmt", "yuv420p", clip])
            clips.append(clip)
        log(f"built {len(clips)} scene clips; joining + audio + captions")

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
                "-c:a", "aac", "-b:a", "160k", "-shortest",
                "-map", "0:v:0", "-map", "1:a:0", final]
        _run(cmd, cwd=work)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.copyfile(final, out_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size_mb = os.path.getsize(out_path) / 1e6
    log(f"video rendered: {size_mb:.1f} MB -> {os.path.basename(out_path)}")
    return out_path
