# -*- coding: utf-8 -*-
"""Image generation via Gemini 2.5 Flash Image ('Nano Banana'), BYOK.

One request per prompt → a JPEG saved as img-001.jpg, img-002.jpg, … Failures are
logged and skipped so one bad frame doesn't sink the batch. Other providers (fal,
Replicate) can slot in behind the same generate() shape.
"""
import base64, os, time
import httpx

DEFAULT_MODEL = os.environ.get("FABULA_IMAGE_MODEL", "gemini-2.5-flash-image")
_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent?key={key}")


def _one(model, key, prompt, out_path, retries=2):
    url = _ENDPOINT.format(model=model, key=key)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]}}
    last = None
    for attempt in range(1, retries + 2):
        with httpx.Client(timeout=180) as c:
            r = c.post(url, json=body, headers={"Content-Type": "application/json"})
        if r.status_code >= 400:
            last = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            if r.status_code in (400, 401, 403):   # config/auth — don't retry
                raise last
            time.sleep(1.5 * attempt); continue
        parts = r.json()["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(inline["data"]))
                return True
        last = RuntimeError("no image in response")
        time.sleep(1.2 * attempt)
    if last:
        raise last
    return False


def generate_gemini(prompts, out_dir, api_key, model=None, log=lambda m: None):
    model = model or DEFAULT_MODEL
    os.makedirs(out_dir, exist_ok=True)
    paths, failed = [], 0
    for i, prompt in enumerate(prompts, 1):
        out = os.path.join(out_dir, f"img-{i:03d}.jpg")
        try:
            if _one(model, api_key, prompt, out):
                paths.append(out)
        except Exception as e:
            failed += 1
            log(f"  img-{i:03d} failed: {str(e)[:80]}")
            if i == 1:            # first one failing = almost always key/config → stop early
                raise
    log(f"images: {len(paths)} ok, {failed} failed")
    return paths
