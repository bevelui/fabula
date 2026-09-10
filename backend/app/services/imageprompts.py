# -*- coding: utf-8 -*-
"""Turn a narrated story into N image prompts with consistent characters.

Claude segments the story into ordered visual scenes and defines each recurring
character ONCE; Python then assembles every final prompt as
    <style prefix> + <character descriptions, verbatim> + <scene action>
so a character looks the same across every image, in whatever art style. Prompts
are always English (image models prefer it) even when the story is in another language.
"""
import json, re, httpx

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

_SYSTEM = """You convert a narrated story into image-generation scenes for an \
illustrated video, keeping characters visually consistent across scenes.

Return ONLY a JSON object with two keys:
"characters": object mapping a STABLE UPPERCASE_SNAKE key to a fixed English visual \
description (age, build, hair, face, clothing, demeanour). Every person appearing in \
more than one scene MUST have an entry. Descriptions are reused verbatim, so make them \
complete. Do NOT include the art style — that is added separately.
"scenes": an array, in story order, each: { "chars": [character keys present, [] if none], \
"action": "a concise ENGLISH description of what this shot shows" }.
Rules: English only for all descriptions and actions, whatever the story's language. \
Produce EXACTLY the requested number of scenes, covering the whole story in order. \
One-off background people may be described inline in "action" with chars []. \
Never put text, letters or signage in a scene."""


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text); text = re.sub(r"\n?```$", "", text).strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        raise RuntimeError("no JSON in prompt-builder response")
    return json.loads(text[i:j + 1])


def build_scene_prompts(script, language, style_prefix, n_scenes, api_key, log=lambda m: None):
    user = (f"Story language: {language}. Break this story into EXACTLY {n_scenes} scenes.\n\n"
            f"STORY:\n{script}\n\nReturn the JSON now.")
    body = json.dumps({
        "model": MODEL, "max_tokens": 8000, "system": _SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    log(f"planning {n_scenes} scenes with consistent characters (Claude)")
    with httpx.Client(timeout=180) as c:
        r = c.post(API, content=body, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        r.raise_for_status()
        data = r.json()
    spec = _parse("".join(b.get("text", "") for b in data.get("content", [])))
    chars = spec.get("characters") or {}
    scenes = spec.get("scenes") or spec.get("shots") or []
    prompts = assemble(chars, scenes, style_prefix)
    log(f"{len(prompts)} scene prompts built; {len(chars)} recurring characters")
    return prompts


def _as_text(v):
    """Coerce a character/action value to a plain string, whatever shape the model used."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for f in ("description", "desc", "appearance", "look", "text", "value", "name"):
            if isinstance(v.get(f), str):
                return v[f].strip()
        return " ".join(str(x).strip() for x in v.values() if isinstance(x, str))
    if isinstance(v, list):
        return " ".join(_as_text(x) for x in v)
    return str(v).strip()


def assemble(chars, scenes, style_prefix):
    """Compose final prompts: style prefix + character descriptions (verbatim) + action.
    Tolerant of the model returning characters/chars as strings, dicts, or lists."""
    out = []
    for s in scenes:
        s = s if isinstance(s, dict) else {"action": s}
        keys = s.get("chars") or s.get("characters") or []
        if isinstance(keys, str):
            keys = [keys]
        parts = []
        for k in keys:
            if isinstance(k, dict):
                kk = k.get("key") or k.get("name") or ""
                parts.append(_as_text(chars.get(kk) or k))
            else:
                parts.append(_as_text(chars.get(k, k)))
        who = " and ".join(p for p in parts if p)
        action = _as_text(s.get("action") or s.get("description") or "")
        out.append(" ".join(f"{style_prefix} {who} {action}".split()))
    return out
