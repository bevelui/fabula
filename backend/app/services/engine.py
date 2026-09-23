# -*- coding: utf-8 -*-
"""The generation pipeline, as a list of ordered stages a job runs through.

At scaffold stage each stage is a lightweight placeholder that exercises the real
plumbing — it resolves the chosen language and art style, logs what it *would* call,
and produces a small artifact — so the whole project → job → worker → status flow is
end-to-end runnable without burning API credits. Wiring each stage to the real
provider (YouTube Data API, LLM, Fish, image API, Remotion render) is the next step;
the signatures below are where that code lands.
"""
import os, time
import httpx
from .. import catalog
from ..config import settings
from . import youtube, llm, tts, imageprompts, image_gen, captions as captions_svc, thumbnail as thumb_svc, render as render_svc, render_ffmpeg, render_remote, render_remotion, storage
import glob, re, math


def _naive_scene_prompts(script, style_prefix, n):
    """Fallback when there's no LLM key: split the story into N chunks, no character sheet."""
    sents = re.split(r"(?<=[.!?…])\s+", script.strip())
    if not sents:
        return []
    per = max(1, len(sents) // n)
    chunks, i = [], 0
    while i < len(sents) and len(chunks) < n:
        chunk = " ".join(sents[i:i + per]).strip()
        if chunk:
            chunks.append(" ".join(f"{style_prefix} {chunk}".split()))
        i += per
    return chunks[:n] or [f"{style_prefix} {script[:200]}"]


def _project_out(project):
    d = os.path.join(settings.OUTPUT_DIR, project["id"])
    os.makedirs(d, exist_ok=True)
    return d


def _scene_count(project, artifacts):
    """How many images. User's exact choice if set, else auto so each still gets at most
    ~SECONDS_PER_IMAGE of screen time (based on the real narration length)."""
    chosen = project.get("num_images") or 0
    if chosen and int(chosen) > 0:
        return max(1, min(200, int(chosen)))
    sec = catalog.fmt(project.get("format")).get("sec_per_image", 20)   # short=5s, long=20s
    dur = captions_svc.audio_duration(artifacts.get("audio"))
    if not dur:                                   # no audio yet → estimate from words (~145 wpm)
        words = artifacts.get("script_words") or project.get("length_words") or 1200
        dur = words / 145.0 * 60.0
    return max(4, min(200, math.ceil(dur / sec)))

# (key, human label). Order is the pipeline order.
STAGES = [
    ("analyze",   "Analyze channel"),
    ("script",    "Write script"),
    ("audio",     "Generate narration"),
    ("images",    "Generate images"),
    ("captions",  "Build captions"),
    ("video",     "Render video"),
    ("thumbnail", "Make thumbnail"),
]


def run_stage(key, project, log, keys=None, artifacts=None):
    """Run one stage. `log(msg)` appends a line. `keys` = {provider: plaintext} BYOK.
    `artifacts` = accumulated outputs from earlier stages. Returns new artifacts."""
    keys = keys or {}
    artifacts = artifacts or {}
    lang = project.get("language", "en")
    style = catalog.style_prompt(project.get("style_id", "ink-wash"),
                                 project.get("style_custom"))

    if key == "analyze":                       # REAL — public RSS, no key needed
        if (project.get("script_source") or "channel") == "own" or not (project.get("channel_url") or "").strip():
            log("using your own script — skipping channel analysis")
            return {"style_profile": {}}
        profile = youtube.analyze(project.get("channel_url", ""), log)
        cad = profile.get("cadence") or {}
        log(f"keywords: {', '.join(profile['top_keywords'][:8])}")
        if cad:
            log(f"cadence: ~{cad['per_week']} uploads/week; avg title {profile['avg_title_words']} words")
        return {"style_profile": profile}

    if key == "script":                        # REAL — own script or Claude-written
        src = project.get("script_source") or "channel"
        mdl = project.get("script_model") or "claude-sonnet-5"
        us = (project.get("user_script") or "").strip()
        mode = project.get("script_mode") or "asis"
        length = project.get("length_words", 1200)
        try:
            if src == "own":
                if not us:
                    log("[skipped] no script provided")
                    return {"script": None, "script_status": "no_user_script"}
                if mode == "asis":
                    text = us
                    log(f"using your script as-is: {len(text.split())} words (free, no key)")
                else:
                    api_key = keys.get("anthropic")
                    if not api_key:
                        log("[skipped] polish/reference needs your Claude key (or use 'as-is')")
                        return {"script": None, "script_status": "needs_anthropic_key"}
                    if mode == "polish":
                        text = llm.polish_script(us, lang, api_key, log, model=mdl)
                    else:
                        text = llm.script_from_reference(us, lang, length, api_key, log, model=mdl)
                    log(f"script ready: {len(text.split())} words")
            else:
                api_key = keys.get("anthropic")
                if not api_key:
                    log("[skipped] no Anthropic (Claude) key in your BYOK vault — add one to enable")
                    return {"script": None, "script_status": "needs_anthropic_key"}
                profile = artifacts.get("style_profile", {})
                text = llm.generate_script(profile, lang, length, api_key, log, model=mdl)
                log(f"script generated: {len(text.split())} words")
        except httpx.HTTPStatusError as e:
            log(f"[failed] Claude returned {e.response.status_code}")
            return {"script": None, "script_status": f"http_{e.response.status_code}"}
        except Exception as e:
            log(f"[failed] script error: {str(e)[:140]}")
            return {"script": None, "script_status": "script_error"}
        script_path = os.path.join(_project_out(project), "script.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(text)
        return {"script": text, "script_words": len(text.split()), "script_file": script_path}

    if key == "audio":                         # REAL — provider-dispatched TTS
        text = artifacts.get("script")
        if not text:
            log("[skipped] no script text from the previous stage")
            return {"audio": None, "audio_status": "no_script"}
        prov = catalog.audio_provider(project.get("audio_provider") or "edge")
        need = prov["key"]
        if need and not keys.get(need):
            log(f"[skipped] '{prov['name']}' needs your {need} key (or switch to a free voice engine)")
            return {"audio": None, "audio_status": f"needs_{need}_key"}
        if prov["id"] in ("fish", "elevenlabs") and not project.get("voice_id"):
            log(f"[skipped] '{prov['name']}' needs a voice id on the project")
            return {"audio": None, "audio_status": "needs_voice_id"}
        out = os.path.join(_project_out(project), "narration.mp3")
        try:
            path, nbytes, segs = tts.synthesize(prov["id"], text, project.get("voice_id"),
                                                 lang, keys, out, log=log)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            log(f"[failed] {prov['name']} returned {code} — check the key/voice or try a free engine")
            return {"audio": None, "audio_status": f"http_{code}"}
        except Exception as e:
            log(f"[failed] narration error: {str(e)[:140]}")
            return {"audio": None, "audio_status": "audio_error"}
        log(f"narration saved: {nbytes/1000:.0f} KB -> {os.path.basename(path)}")
        return {"audio": path, "audio_bytes": nbytes, "caption_segments": segs or None}

    if key == "images":                        # REAL — provider-dispatched image gen
        script = artifacts.get("script")
        if not script:
            log("[skipped] no script text to illustrate")
            return {"images": None, "images_status": "no_script"}
        prov = catalog.image_provider(project.get("image_provider") or "pollinations")
        need = prov["key"]
        if need and not keys.get(need):
            log(f"[skipped] '{prov['name']}' needs your {need} key (or switch to the free engine)")
            return {"images": None, "images_status": f"needs_{need}_key"}
        n = _scene_count(project, artifacts)
        out = os.path.join(_project_out(project), "images")
        an = keys.get("anthropic")
        mdl = project.get("scene_model") or "claude-sonnet-5"
        dims = catalog.fmt(project.get("format")).get("img", (1920, 1080))
        # Reference-locked characters: fal + Claude planner + R2 (references passed by URL).
        locked = (bool(project.get("lock_characters")) and prov["id"] == "fal"
                  and an and storage.enabled())

        def _save_prompts(prompts):
            with open(os.path.join(_project_out(project), "prompts.txt"), "w", encoding="utf-8") as f:
                for i, p in enumerate(prompts, 1):
                    f.write(f"--- scene {i} ---\n{p}\n\n")

        try:
            if locked:
                log("consistent-characters mode: fal reference-locking is ON")
                chars, scenes = imageprompts.build_scene_spec(script, lang, n, an, log, model=mdl)
                prompts = imageprompts.assemble(chars, scenes, style)
                _save_prompts(prompts)
                paths = image_gen.generate_locked(keys["fal"], chars, scenes, style, out,
                                                  project["id"], size=dims, log=log)
                return {"images": out, "image_count": len(paths),
                        "scene_prompts": prompts, "locked_characters": True}
            if an:
                try:
                    prompts = imageprompts.build_scene_prompts(script, lang, style, n, an, log, model=mdl)
                except Exception as e:
                    log(f"scene planner had trouble ({str(e)[:120]}) — using a simple scene split so images still generate")
                    prompts = _naive_scene_prompts(script, style, n)
            else:
                log("no Claude key — using a simple scene split (add Claude for consistent characters)")
                prompts = _naive_scene_prompts(script, style, n)
            _save_prompts(prompts)
            paths = image_gen.generate(prov["id"], prompts, out, keys, log=log, size=dims)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            log(f"[failed] {prov['name']} returned {code} — check the relevant key")
            return {"images": None, "images_status": f"http_{code}"}
        except Exception as e:
            log(f"[failed] image generation error: {str(e)[:140]}")
            return {"images": None, "images_status": "error"}
        return {"images": out, "image_count": len(paths), "scene_prompts": prompts}

    if key == "captions":                      # REAL — pure Python, no key
        text = artifacts.get("script")
        if not text:
            log("[skipped] no script text to caption")
            return {"captions": None, "captions_status": "no_script"}
        segs = artifacts.get("caption_segments")
        if segs:
            log(f"using {len(segs)} real voice segments — captions locked to the audio")
            res = captions_svc.build_from_segments(segs, _project_out(project), log=log)
        else:
            audio = artifacts.get("audio")
            dur = captions_svc.audio_duration(audio)
            if dur:
                log(f"using real audio duration: {dur:.0f}s (estimated word pacing)")
            else:
                dur = max(1.0, len(text.split()) / captions_svc.WPM_ESTIMATE * 60.0)
                log(f"no audio yet — estimating {dur:.0f}s from word count")
            res = captions_svc.build_captions(text, dur, _project_out(project), log=log)
        return {"captions_json": res["captions_json"], "srt": res["srt"],
                "caption_words": res["words"], "srt_cues": res["srt_cues"]}

    if key == "video":                         # REAL — ffmpeg (default) or Remotion
        imgs = artifacts.get("images")
        audio = artifacts.get("audio")
        srt = artifacts.get("srt")
        caps = artifacts.get("captions_json")
        need = {"images": imgs, "audio": audio, "captions": caps}
        missing = [n for n, v in need.items() if not v]
        if missing:
            log(f"[skipped] need {', '.join(missing)} from earlier stages")
            return {"video": None, "video_status": "missing_" + "_".join(missing)}
        out = os.path.join(_project_out(project), "video.mp4")
        engine = catalog.render_engine(project.get("render_engine") or settings.RENDER_ENGINE)
        vdims = catalog.video_dims(project.get("format"), project.get("resolution"))
        log(f"output: {vdims[0]}x{vdims[1]} ({catalog.resolution(project.get('resolution'))}p)")
        # Dispatch to the dedicated render worker when one is configured; else render here.
        if settings.RENDER_WORKER_URL:
            render_remote.render_via_worker(project, imgs, audio, srt, out, engine, log)
            return {"video": out, "render_engine": engine}
        if engine == "remotion":
            if settings.REMOTION_ENABLED and os.path.isdir(os.path.join(settings.REMOTION_DIR, "src")):
                render_remotion.render_video(imgs, audio, caps, out, size=vdims, log=log)
            else:
                log("Cinematic (Remotion) isn't enabled on this server yet (needs Node + the "
                    "render worker) — rendering with the standard engine instead")
                render_ffmpeg.render_video(imgs, audio, srt, out, log, size=vdims)
                engine = "ffmpeg"
        else:
            render_ffmpeg.render_video(imgs, audio, srt, out, log, size=vdims)
        return {"video": out, "render_engine": engine}

    if key == "thumbnail":                     # REAL — PIL, no key
        imgs_dir = artifacts.get("images")
        frames = sorted(glob.glob(os.path.join(imgs_dir, "img-*.jpg"))) if imgs_dir else []
        if not frames:
            log("[skipped] no generated images to build a thumbnail from")
            return {"thumbnail": None, "thumbnail_status": "no_images"}
        base = frames[int(len(frames) * 0.62)]   # a late, climax-ish frame
        quote = project.get("title") or "Una historia que no olvidarás"
        out = os.path.join(_project_out(project), "thumbnail.jpg")
        thumb_svc.make_thumbnail(base, quote, out, kicker="", log=log)
        return {"thumbnail": out}

    log(f"[warn] unknown stage {key}")
    return {}
