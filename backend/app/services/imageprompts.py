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

_SYSTEM = """You are a cinematographer turning a narrated story into vivid, varied \
image-generation scenes for an illustrated video. Keep characters visually consistent \
across scenes, and make each shot cinematic.

Return ONLY a JSON object with two keys:
"characters": object mapping a STABLE UPPERCASE_SNAKE key to a fixed, detailed English \
visual description (age, build, hair, face, distinguishing features, exact clothing, \
demeanour). Every person appearing in more than one scene MUST have an entry, and the \
description is reused VERBATIM every time, so make it complete and specific enough that \
the same person is recognisable. Do NOT include the art style — that is added separately.
"scenes": an array, in story order, each: { "chars": [character keys present in this \
shot, in order; [] if none], "action": "a concise but vivid ENGLISH description of the \
shot" }.
Make the "action" cinematic and specific: name the SHOT TYPE (wide establishing, medium, \
close-up, over-the-shoulder), the characters' POSE and EXPRESSION and what they are DOING, \
their SPATIAL relationship in multi-character scenes (who is left/right, foreground/back), \
the SETTING and TIME OF DAY, and the LIGHTING and MOOD. Vary the shot types across scenes. \
Put the right people in each shot via "chars" (2+ keys for multi-character scenes).
Rules: English only, whatever the story's language. Produce EXACTLY the requested number \
of scenes, covering the whole story in order. One-off background people may be described \
inline in "action" with chars []. Never depict text, letters, captions or signage."""


def _balanced(s, open_idx):
    """Return the balanced {...} substring starting at open_idx (a '{'), or None."""
    depth = 0
    for idx in range(open_idx, len(s)):
        if s[idx] == "{":
            depth += 1
        elif s[idx] == "}":
            depth -= 1
            if depth == 0:
                return s[open_idx:idx + 1]
    return None


def _salvage(frag):
    """Recover what we can when the whole response isn't valid JSON: parse the
    characters object and EACH scene object independently, skipping any single
    malformed one (an unescaped quote in one scene shouldn't lose all the others)."""
    chars = {}
    m = re.search(r'"characters"\s*:\s*\{', frag)
    if m:
        obj = _balanced(frag, m.end() - 1)
        if obj:
            try:
                chars = json.loads(obj)
            except Exception:
                chars = {}
    scenes, depth, start = [], 0, None
    m = re.search(r'"scenes"\s*:\s*\[', frag)
    search_from = m.end() if m else 0
    for idx in range(search_from, len(frag)):
        ch = frag[idx]
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    scenes.append(json.loads(frag[start:idx + 1]))
                except Exception:
                    pass
                start = None
        elif ch == "]" and depth == 0 and m:
            break
    if not scenes:
        raise RuntimeError("could not parse any scenes from the prompt-builder response")
    return {"characters": chars, "scenes": scenes}


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text); text = re.sub(r"\n?```$", "", text).strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0:
        raise RuntimeError("no JSON in prompt-builder response")
    if j > i:
        try:
            return json.loads(text[i:j + 1])          # fast path: valid JSON
        except Exception:
            pass
    return _salvage(text[i:])                          # tolerant path: skip bad scenes


def build_scene_spec(script, language, n_scenes, api_key, log=lambda m: None, model=MODEL):
    """Ask Claude for the structured {characters, scenes} plan. characters is
    {KEY: plain-text description}; scenes is [{chars:[keys], action}]."""
    user = (f"Story language: {language}. Break this story into EXACTLY {n_scenes} scenes.\n\n"
            f"STORY:\n{script}\n\nReturn the JSON now. Use plain straight text in every string; "
            f"do not use double quotes inside a description (paraphrase instead) so the JSON stays valid.")
    # scale the budget with scene count so long videos don't get truncated mid-array
    max_tokens = min(16000, 2500 + n_scenes * 350)
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": _SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    log(f"planning {n_scenes} cinematic scenes with consistent characters ({model})")
    with httpx.Client(timeout=180) as c:
        r = c.post(API, content=body, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        r.raise_for_status()
        data = r.json()
    spec = _parse("".join(b.get("text", "") for b in data.get("content", [])))
    raw = spec.get("characters") or {}
    chars = {k: _as_text(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    scenes = spec.get("scenes") or spec.get("shots") or []
    return chars, scenes


def build_scene_prompts(script, language, style_prefix, n_scenes, api_key,
                        log=lambda m: None, model=MODEL):
    chars, scenes = build_scene_spec(script, language, n_scenes, api_key, log, model)
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
