# -*- coding: utf-8 -*-
"""Script generation via the Claude API (Anthropic Messages), using the caller's
BYOK key. Writes an original story in the requested language, guided by the style
profile derived from the channel — never copying source content.
"""
import json, httpx

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

_LANG_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German",
               "nl": "Dutch", "it": "Italian", "pt": "Portuguese", "pl": "Polish",
               "sv": "Swedish", "id": "Indonesian"}


def generate_script(profile, language, length_words, api_key, log=lambda m: None):
    lang = _LANG_NAMES.get(language, language)
    kws = ", ".join(profile.get("top_keywords", [])[:10]) or "(none)"
    samples = "\n".join("- " + t for t in profile.get("sample_titles", [])[:8])
    system = (
        "You are a scriptwriter for a faceless narrated-story YouTube channel. "
        "Write an ORIGINAL story script for narration — never copy or paraphrase any "
        "existing video. Match the channel's niche and tone, not its wording. "
        f"Write entirely in {lang}. Return only the narration text, no headings or notes."
    )
    user = (
        f"Channel niche signals derived from public metadata:\n"
        f"- recurring keywords: {kws}\n"
        f"- example titles (for tone only, do not reuse):\n{samples}\n\n"
        f"Write a self-contained emotional story of about {length_words} words in {lang}. "
        f"Natural spoken narration, a strong hook in the first two sentences, a turning "
        f"point, and a resonant ending."
    )
    body = json.dumps({
        "model": MODEL, "max_tokens": min(8000, int(length_words * 2.2) + 500),
        "system": system, "messages": [{"role": "user", "content": user}],
    }).encode()
    log(f"calling Claude ({MODEL}) for a ~{length_words}-word script in {lang}")
    with httpx.Client(timeout=180) as c:
        r = c.post(API, content=body, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        r.raise_for_status()
        data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []))
    return text.strip()
