# -*- coding: utf-8 -*-
"""Script generation via the Claude API (Anthropic Messages), using the caller's
BYOK key. Modes: write from a channel profile, polish the user's own script, or
write a new original script in the style of the user's reference script.
"""
import json, httpx

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

_LANG_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German",
               "nl": "Dutch", "it": "Italian", "pt": "Portuguese", "pl": "Polish",
               "sv": "Swedish", "id": "Indonesian"}


def _complete(system, user, api_key, model, max_tokens, log=lambda m: None):
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    with httpx.Client(timeout=300) as c:
        r = c.post(API, content=body, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        r.raise_for_status()
        data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def generate_script(profile, language, length_words, api_key, log=lambda m: None, model=MODEL):
    lang = _LANG_NAMES.get(language, language)
    kws = ", ".join(profile.get("top_keywords", [])[:10]) or "(none)"
    samples = "\n".join("- " + t for t in profile.get("sample_titles", [])[:8])
    system = (
        "You are a scriptwriter for a faceless narrated-story YouTube channel. "
        "Write an ORIGINAL story script for narration — never copy or paraphrase any "
        "existing video. Match the channel's niche and tone, not its wording. "
        f"Write entirely in {lang}. Return only the narration text, no headings or notes.")
    user = (f"Channel niche signals derived from public metadata:\n"
            f"- recurring keywords: {kws}\n"
            f"- example titles (for tone only, do not reuse):\n{samples}\n\n"
            f"Write a self-contained emotional story of about {length_words} words in {lang}. "
            f"Natural spoken narration, a strong hook in the first two sentences, a turning "
            f"point, and a resonant ending.")
    log(f"calling Claude ({model}) for a ~{length_words}-word script in {lang}")
    return _complete(system, user, api_key, model, min(8000, int(length_words * 2.2) + 500), log)


def polish_script(user_script, language, api_key, log=lambda m: None, model=MODEL):
    """Improve the user's own script without changing the story or meaning."""
    lang = _LANG_NAMES.get(language, language)
    system = ("You are a careful script editor for narrated story videos. Improve the "
              "prose, flow, rhythm and hook of the script WITHOUT changing its story, "
              "characters, facts or meaning. Keep roughly the same length. "
              f"Write in {lang}. Return only the improved narration text, nothing else.")
    log(f"polishing your script with Claude ({model})")
    n = min(8000, len(user_script.split()) * 2 + 800)
    return _complete(system, "SCRIPT TO IMPROVE:\n\n" + user_script, api_key, model, n, log)


def script_from_reference(reference, language, length_words, api_key, log=lambda m: None, model=MODEL):
    """Write a NEW original script in the style/structure of the reference script."""
    lang = _LANG_NAMES.get(language, language)
    system = ("You are a scriptwriter for narrated story videos. Use the provided script "
              "ONLY as a STYLE and STRUCTURE reference — its tone, pacing, hook and emotional "
              "arc. Write a NEW, ORIGINAL story: do not reuse its plot, names, or wording. "
              f"About {length_words} words, entirely in {lang}. Return only the narration.")
    log(f"writing a new script in your reference's style with Claude ({model})")
    n = min(8000, int(length_words * 2.2) + 500)
    return _complete(system, "REFERENCE SCRIPT (style only):\n\n" + reference, api_key, model, n, log)
