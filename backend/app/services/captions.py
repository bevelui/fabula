# -*- coding: utf-8 -*-
"""Captions from the exact narration text — no ASR, no provider, no key.

Char-weighted proportional per-word timing across the audio duration → a Remotion
word-timing captions.json plus a YouTube .srt. Language-agnostic for space-delimited
scripts (Latin-script launch languages). Uses the real mp3 duration when available
(PyAV, else ffprobe), otherwise estimates from word count.
"""
import os, re, json, subprocess

WPM_ESTIMATE = 130  # words/min fallback when there is no audio yet


def audio_duration(path):
    if not path or not os.path.exists(path):
        return None
    try:
        import av
        with av.open(path) as c:
            if c.duration:
                return c.duration / 1_000_000.0
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path], text=True)
        return float(out.strip())
    except Exception:
        return None


def _srt_ts(ms):
    h = ms // 3600000; ms %= 3600000
    m = ms // 60000; ms %= 60000
    s = ms // 1000; ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_captions(text, duration_s, out_dir, label="video", log=lambda m: None):
    os.makedirs(out_dir, exist_ok=True)
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    weights = [len(w) + 1 for w in words]
    total = sum(weights) or 1
    dur_ms = duration_s * 1000.0

    caps, t = [], 0.0
    for w, wt in zip(words, weights):
        span = dur_ms * wt / total
        start, end = int(t), int(t + span)
        caps.append({"text": " " + w, "startMs": start, "endMs": end,
                     "timestampMs": (start + end) // 2, "confidence": 1})
        t += span

    cj = os.path.join(out_dir, "captions.json")
    with open(cj, "w", encoding="utf-8") as f:
        json.dump(caps, f, ensure_ascii=False)

    # group words into readable lines (sentence-end / <=8 words / <=4.5s)
    lines, cur, cur_start = [], [], None
    for c in caps:
        w = c["text"].strip()
        if cur_start is None:
            cur_start = c["startMs"]
        cur.append(w)
        if w[-1:] in ".?!…" or len(cur) >= 8 or (c["endMs"] - cur_start) >= 4500:
            lines.append((cur_start, c["endMs"], " ".join(cur)))
            cur, cur_start = [], None
    if cur:
        lines.append((cur_start, caps[-1]["endMs"], " ".join(cur)))

    srt = os.path.join(out_dir, f"{label}.srt")
    with open(srt, "w", encoding="utf-8") as f:
        for i, (st, en, tx) in enumerate(lines, 1):
            f.write(f"{i}\n{_srt_ts(st)} --> {_srt_ts(en)}\n{tx}\n\n")

    log(f"captions: {len(caps)} words over {duration_s:.0f}s -> {len(lines)} subtitle cues")
    return {"captions_json": cj, "srt": srt, "words": len(caps), "srt_cues": len(lines)}
