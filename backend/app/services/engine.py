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
from . import youtube, llm, tts, imageprompts, images, captions as captions_svc, thumbnail as thumb_svc, render as render_svc, render_ffmpeg
import glob


def _project_out(project):
    d = os.path.join(settings.OUTPUT_DIR, project["id"])
    os.makedirs(d, exist_ok=True)
    return d


def _scene_count(project, artifacts):
    """How many images to make — roughly one per ~120 narration words, 8..60."""
    words = artifacts.get("script_words") or project.get("length_words") or 1200
    return max(8, min(60, round(words / 120)))

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
        profile = youtube.analyze(project.get("channel_url", ""), log)
        cad = profile.get("cadence") or {}
        log(f"keywords: {', '.join(profile['top_keywords'][:8])}")
        if cad:
            log(f"cadence: ~{cad['per_week']} uploads/week; avg title {profile['avg_title_words']} words")
        return {"style_profile": profile}

    if key == "script":                        # REAL — Claude via BYOK
        api_key = keys.get("anthropic")
        if not api_key:
            log("[skipped] no Anthropic (Claude) key in your BYOK vault — add one to enable")
            return {"script": None, "script_status": "needs_anthropic_key"}
        profile = artifacts.get("style_profile", {})
        text = llm.generate_script(profile, lang, project.get("length_words", 1200),
                                   api_key, log)
        log(f"script generated: {len(text.split())} words")
        return {"script": text, "script_words": len(text.split())}

    if key == "audio":                         # REAL — Fish Audio via BYOK
        text = artifacts.get("script")
        if not text:
            log("[skipped] no script text from the previous stage")
            return {"audio": None, "audio_status": "no_script"}
        api_key = keys.get("fish")
        voice = project.get("voice_id")
        if not api_key or not voice:
            missing = "Fish key" if not api_key else "voice_id"
            log(f"[skipped] need your {missing} (add a 'fish' key + set the project voice)")
            return {"audio": None, "audio_status": "needs_fish_key_and_voice"}
        out = os.path.join(_project_out(project), "narration.mp3")
        try:
            path, nbytes = tts.synthesize_fish(text, voice, api_key, out, log=log)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            hint = "check your Fish key" if code in (401, 403) else \
                   "check the voice id" if code in (400, 404) else "try again"
            log(f"[failed] Fish returned {code} — {hint}")
            return {"audio": None, "audio_status": f"fish_http_{code}"}
        except Exception as e:
            log(f"[failed] Fish request error: {str(e)[:120]}")
            return {"audio": None, "audio_status": "fish_error"}
        log(f"narration saved: {nbytes/1000:.0f} KB -> {os.path.basename(path)}")
        return {"audio": path, "audio_bytes": nbytes}

    if key == "images":                        # REAL — Claude scenes + Gemini render, BYOK
        script = artifacts.get("script")
        if not script:
            log("[skipped] no script text to illustrate")
            return {"images": None, "images_status": "no_script"}
        an, gm = keys.get("anthropic"), keys.get("gemini")
        if not an or not gm:
            missing = "Anthropic (Claude)" if not an else "Gemini"
            log(f"[skipped] need your {missing} key (scenes use Claude, images use Gemini)")
            return {"images": None, "images_status": "needs_keys"}
        n = _scene_count(project, artifacts)
        out = os.path.join(_project_out(project), "images")
        try:
            prompts = imageprompts.build_scene_prompts(script, lang, style, n, an, log)
            paths = images.generate_gemini(prompts, out, gm, log=log)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            log(f"[failed] image provider returned {code} — check the relevant key")
            return {"images": None, "images_status": f"http_{code}"}
        except Exception as e:
            log(f"[failed] image generation error: {str(e)[:120]}")
            return {"images": None, "images_status": "error"}
        return {"images": out, "image_count": len(paths)}

    if key == "captions":                      # REAL — pure Python, no key
        text = artifacts.get("script")
        if not text:
            log("[skipped] no script text to caption")
            return {"captions": None, "captions_status": "no_script"}
        audio = artifacts.get("audio")
        dur = captions_svc.audio_duration(audio)
        if dur:
            log(f"using real audio duration: {dur:.0f}s")
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
        try:
            if settings.RENDER_ENGINE == "remotion":
                if not os.path.isdir(settings.REMOTION_PROJECT):
                    log("[skipped] Remotion project not available on this server")
                    return {"video": None, "video_status": "render_disabled"}
                render_svc.render_video(imgs, audio, caps, out, log)
            else:
                render_ffmpeg.render_video(imgs, audio, srt, out, log)
        except Exception as e:
            log(f"[failed] render error: {str(e)[:160]}")
            return {"video": None, "video_status": "render_error"}
        return {"video": out}

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
