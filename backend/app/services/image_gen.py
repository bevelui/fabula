# -*- coding: utf-8 -*-
"""Image generation across providers. One prompt -> img-NNN.jpg.

  pollinations : FREE, no key (Flux under the hood)
  gemini       : Gemini 2.5 Flash Image ('Nano Banana') — needs billing
  openai       : gpt-image-1 (DALL·E family)

Failures are logged and skipped; a first-image failure raises (usually key/quota).
"""
import base64, os, time, urllib.parse, random
import httpx

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
    else:
        # Gemini image has no size param — steer it with an aspect hint
        if h > w:
            prompt = prompt + " Vertical 9:16 full-frame composition."
        elif w > h:
            prompt = prompt + " Wide 16:9 full-frame composition."
        _gemini(prompt, out, keys["gemini"])


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
