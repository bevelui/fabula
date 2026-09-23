# -*- coding: utf-8 -*-
"""Image generation across providers. One prompt -> img-NNN.jpg.

  pollinations : FREE, no key (Flux under the hood)
  gemini       : Gemini 2.5 Flash Image ('Nano Banana') — needs billing
  openai       : gpt-image-1 (DALL·E family)
  fal          : fal.ai — Flux for images + nano-banana/edit for LOCKED characters

Failures are logged and skipped; a first-image failure raises (usually key/quota).
"""
import base64, os, re, time, urllib.parse, random
import httpx
from ..config import settings
from . import storage

GEMINI_MODEL = os.environ.get("FABULA_IMAGE_MODEL", "gemini-2.5-flash-image")
_GEMINI_EP = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent?key={key}")


def _save(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _pollinations(prompt, out_path, w, h):
    p = prompt[:900]                                   # keep the URL sane
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(p)
    r = httpx.get(url, params={"width": w, "height": h, "nologo": "true",
                               "model": "flux", "seed": random.randint(1, 10**9)},
                  timeout=180, follow_redirects=True)
    r.raise_for_status()
    _save(out_path, r.content)


def _openai(prompt, out_path, key, w, h):
    size = "1024x1536" if h > w else ("1536x1024" if w > h else "1024x1024")
    r = httpx.post("https://api.openai.com/v1/images/generations",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": "gpt-image-1", "prompt": prompt[:4000],
                         "size": size, "n": 1}, timeout=180)
    r.raise_for_status()
    d = r.json()["data"][0]
    if d.get("b64_json"):
        _save(out_path, base64.b64decode(d["b64_json"]))
    else:
        _save(out_path, httpx.get(d["url"], timeout=120).content)


def _gemini(prompt, out_path, key):
    r = httpx.post(_GEMINI_EP.format(model=GEMINI_MODEL, key=key),
                   json={"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseModalities": ["IMAGE"]}},
                   headers={"Content-Type": "application/json"}, timeout=180)
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            _save(out_path, base64.b64decode(inline["data"]))
            return
    raise RuntimeError("no image in Gemini response")


def _cap(w, h, mx=1536):
    """Flux likes sizes <= ~1536; scale down keeping aspect (images are only sources)."""
    w, h = int(w), int(h)
    if max(w, h) <= mx:
        return w, h
    s = mx / max(w, h)
    return max(64, int(w * s)) // 8 * 8, max(64, int(h * s)) // 8 * 8


def _aspect(w, h):
    return "9:16" if h > w else ("16:9" if w > h else "1:1")


def _fal_run(model, payload, key):
    r = httpx.post("https://fal.run/" + model,
                   headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                   json=payload, timeout=180)
    r.raise_for_status()
    imgs = (r.json() or {}).get("images") or []
    if not imgs or not imgs[0].get("url"):
        raise RuntimeError("no image in fal response")
    return httpx.get(imgs[0]["url"], timeout=120, follow_redirects=True).content


def _fal_txt2img(prompt, out_path, key, w, h):
    cw, ch = _cap(w, h)
    _save(out_path, _fal_run(settings.FAL_IMAGE_MODEL,
          {"prompt": prompt[:5000], "image_size": {"width": cw, "height": ch},
           "num_images": 1, "output_format": "jpeg"}, key))


def _fal_edit(prompt, out_path, key, image_urls, w, h):
    _save(out_path, _fal_run(settings.FAL_EDIT_MODEL,
          {"prompt": prompt[:5000], "image_urls": image_urls, "aspect_ratio": _aspect(w, h),
           "num_images": 1, "output_format": "jpeg"}, key))


def _retryable(e):
    """Transient errors worth a retry (server hiccups, rate limits, network/timeouts).
    Auth/config errors (400/401/403/404) are not retried."""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (408, 425, 429, 500, 502, 503, 504)
    return True


def _one(provider, prompt, out, keys, w, h):
    if provider == "pollinations":
        _pollinations(prompt, out, w, h)
    elif provider == "openai":
        _openai(prompt, out, keys["openai"], w, h)
    elif provider == "fal":
        _fal_txt2img(prompt, out, keys["fal"], w, h)
    else:
        # Gemini image has no size param — steer it with an aspect hint
        if h > w:
            prompt = prompt + " Vertical 9:16 full-frame composition."
        elif w > h:
            prompt = prompt + " Wide 16:9 full-frame composition."
        _gemini(prompt, out, keys["gemini"])


def generate_one(provider, prompt, out_path, keys, size=(1536, 864), tries=3, log=lambda m: None):
    """Regenerate a single image to a specific path (for the review 'redo' button)."""
    w, h = size
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    last = None
    for attempt in range(1, tries + 1):
        try:
            _one(provider, prompt, out_path, keys, w, h)
            return out_path
        except Exception as e:
            last = e
            if attempt < tries and _retryable(e):
                time.sleep(1.5 * attempt)
            else:
                break
    raise last


def generate(provider, prompts, out_dir, keys, log=lambda m: None, tries=3, size=(1536, 864)):
    w, h = size
    os.makedirs(out_dir, exist_ok=True)
    total = len(prompts)
    log(f"generating {total} images with {provider} — this can take a few minutes…")
    paths, failed = [], 0
    for i, prompt in enumerate(prompts, 1):
        out = os.path.join(out_dir, f"img-{i:03d}.jpg")
        last = None
        for attempt in range(1, tries + 1):
            try:
                _one(provider, prompt, out, keys, w, h)
                paths.append(out)
                last = None
                log(f"  image {i}/{total} ready")
                break
            except Exception as e:
                last = e
                if attempt < tries and _retryable(e):
                    log(f"  img-{i:03d} attempt {attempt} failed ({str(e)[:60]}) — retrying")
                    time.sleep(1.5 * attempt)
                else:
                    break
        if last is not None:
            failed += 1
            log(f"  img-{i:03d} failed after {tries} tries: {str(last)[:80]}")
            if i == 1:                      # first frame failing = key/quota → stop early
                raise last
        time.sleep(0.2)
    log(f"images ({provider}): {len(paths)} ok, {failed} failed")
    return paths


def _retry(fn, tries, log, label):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            if attempt < tries and _retryable(e):
                log(f"  {label} attempt {attempt} failed ({str(e)[:60]}) — retrying")
                time.sleep(1.5 * attempt)
            else:
                break
    raise last


def generate_locked(fal_key, characters, scenes, style_prefix, out_dir, pid,
                    size=(1080, 1920), tries=3, log=lambda m: None):
    """Reference-locked characters (fal): make ONE reference image per character, then
    compose each scene from those references via nano-banana/edit so faces/outfits stay
    consistent. Needs a fal key + R2 (the references are handed to fal as presigned URLs)."""
    if not storage.enabled():
        raise RuntimeError("locked characters need R2 storage (references are passed to fal by URL)")
    w, h = size
    os.makedirs(out_dir, exist_ok=True)
    refs = {}                                   # character key -> presigned reference URL
    if characters:
        log(f"locking {len(characters)} character(s) with reference images…")
    for key, desc in characters.items():
        slug = re.sub(r"[^A-Za-z0-9_-]", "", str(key))[:40] or "char"
        rp = os.path.join(out_dir, f"ref-{slug}.jpg")
        prompt = (f"{style_prefix} Full-length character reference of {desc}. Single figure, "
                  f"front view, neutral plain background, even lighting.")
        _retry(lambda: _fal_txt2img(prompt, rp, fal_key, w, h), tries, log, f"ref {slug}")
        name = f"refs/{slug}.jpg"
        storage.upload_one(pid, rp, name)
        refs[key] = storage.presigned_url(pid, name, expires=6 * 3600)
        log(f"  locked character {key}")

    total = len(scenes)
    log(f"generating {total} scenes with locked characters (fal)…")
    paths, failed = [], 0
    for i, s in enumerate(scenes, 1):
        s = s if isinstance(s, dict) else {"action": s}
        keys = s.get("chars") or s.get("characters") or []
        if isinstance(keys, str):
            keys = [keys]
        action = s.get("action") or s.get("description") or ""
        ref_urls = [refs[k] for k in keys if k in refs]
        out = os.path.join(out_dir, f"img-{i:03d}.jpg")
        try:
            if ref_urls:
                prompt = (f"{style_prefix} {action}. Use the reference image(s) for the "
                          f"characters and keep each one's exact face, hair, build and clothing.")
                _retry(lambda: _fal_edit(prompt, out, fal_key, ref_urls, w, h), tries, log, f"img-{i:03d}")
            else:
                _retry(lambda: _fal_txt2img(f"{style_prefix} {action}", out, fal_key, w, h),
                       tries, log, f"img-{i:03d}")
            paths.append(out)
            log(f"  image {i}/{total} ready")
        except Exception as e:
            failed += 1
            log(f"  img-{i:03d} failed: {str(e)[:80]}")
            if i == 1:
                raise
        time.sleep(0.2)
    log(f"locked images (fal): {len(paths)} ok, {failed} failed")
    return paths
