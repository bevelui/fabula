# -*- coding: utf-8 -*-
"""Text-to-speech across providers -> narration.mp3.

  edge       : FREE, no key (Microsoft Edge voices) — default free option
  fish       : Fish Audio (reference_id voice)
  openai     : OpenAI TTS (voice name e.g. onyx, alloy)
  elevenlabs : ElevenLabs (voice id)
"""
import asyncio
import httpx

FISH_TTS = "https://api.fish.audio/v1/tts"

# a sensible default Edge voice per language when the user gives no voice id
_EDGE_DEFAULT = {
    "en": "en-US-GuyNeural", "es": "es-MX-JorgeNeural", "fr": "fr-FR-HenriNeural",
    "de": "de-DE-ConradNeural", "nl": "nl-NL-MaartenNeural", "it": "it-IT-DiegoNeural",
    "pt": "pt-BR-AntonioNeural", "pl": "pl-PL-MarekNeural", "sv": "sv-SE-MattiasNeural",
    "id": "id-ID-ArdiNeural",
}


def synthesize(provider, text, voice, language, keys, out_path, log=lambda m: None):
    """Returns (path, bytes, word_timings). word_timings is a list of
    {text,startMs,endMs} when the provider reports them (Edge), else None."""
    if provider == "edge":
        return _edge(text, voice or _EDGE_DEFAULT.get(language, "en-US-GuyNeural"), out_path, log)
    if provider == "openai":
        p, n = _openai(text, voice or "onyx", keys["openai"], out_path, log)
        return p, n, None
    if provider == "elevenlabs":
        p, n = _eleven(text, voice, keys["elevenlabs"], out_path, log)
        return p, n, None
    p, n = synthesize_fish(text, voice, keys["fish"], out_path, log=log)
    return p, n, None


def _edge(text, voice, out_path, log):
    """Stream Edge audio AND capture real boundary timings (sentence- or word-level)
    for captions that lock to the voice."""
    import edge_tts, os
    log(f"Edge TTS (free): {len(text)} chars, voice {voice}")
    segs = []

    async def _run():
        comm = edge_tts.Communicate(text, voice)
        with open(out_path, "wb") as f:
            async for ch in comm.stream():
                if ch.get("type") == "audio":
                    f.write(ch["data"])
                elif ch.get("type") in ("SentenceBoundary", "WordBoundary"):
                    st = int(ch["offset"] / 10000)                 # 100ns → ms
                    en = int((ch["offset"] + ch["duration"]) / 10000)
                    segs.append({"text": ch.get("text", ""), "startMs": st, "endMs": en})
    asyncio.run(_run())
    log(f"captured {len(segs)} timed segments from the voice")
    return out_path, os.path.getsize(out_path), segs


def _openai(text, voice, key, out_path, log):
    log(f"OpenAI TTS: {len(text)} chars, voice {voice}")
    with httpx.Client(timeout=300) as c:
        r = c.post("https://api.openai.com/v1/audio/speech",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": "gpt-4o-mini-tts", "voice": voice,
                         "input": text, "response_format": "mp3"})
        r.raise_for_status()
        data = r.content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path, len(data)


def _eleven(text, voice_id, key, out_path, log):
    log(f"ElevenLabs: {len(text)} chars, voice {voice_id}")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    with httpx.Client(timeout=300) as c:
        r = c.post(url, headers={"xi-api-key": key},
                   json={"text": text, "model_id": "eleven_multilingual_v2"})
        r.raise_for_status()
        data = r.content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path, len(data)


def synthesize_fish(text, voice_id, api_key, out_path, model="speech-1.6", log=lambda m: None):
    body = {"text": text, "reference_id": voice_id, "format": "mp3", "mp3_bitrate": 128}
    log(f"Fish TTS: {len(text)} chars, voice {voice_id[:8]}…")
    with httpx.Client(timeout=600) as c:
        r = c.post(FISH_TTS, json=body, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            "model": model})
        r.raise_for_status()
        data = r.content
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path, len(data)
