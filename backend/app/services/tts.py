# -*- coding: utf-8 -*-
"""Text-to-speech via Fish Audio (BYOK). Turns the script into a narration mp3.

Fish needs a `reference_id` (the voice) plus the user's API key — both come from the
user, never hardcoded. Other providers (ElevenLabs, etc.) can slot in behind the same
synthesize() shape later.
"""
import httpx

FISH_TTS = "https://api.fish.audio/v1/tts"


def synthesize_fish(text, voice_id, api_key, out_path, model="speech-1.6", log=lambda m: None):
    body = {"text": text, "reference_id": voice_id, "format": "mp3", "mp3_bitrate": 128}
    log(f"Fish TTS: {len(text)} chars, voice {voice_id[:8]}… -> mp3")
    with httpx.Client(timeout=600) as c:
        r = c.post(FISH_TTS, json=body, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": model,
        })
        r.raise_for_status()
        data = r.content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path, len(data)
