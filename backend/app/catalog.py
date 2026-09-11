# -*- coding: utf-8 -*-
"""The language and art-style catalogs — the user-facing 'any language, any style'.

Language and style are just parameters the engine consumes: language flows to the
script LLM, the TTS voice and the captions; style is a prompt prefix for the image
model. Adding a language or style here surfaces it in the product with no code change.
"""

# Latin-script languages ship at launch (space-delimited words -> caption splitting
# works today). CJK / RTL are marked launch=False until caption + font handling lands.
LANGUAGES = [
    {"code": "en", "name": "English",    "native": "English",    "launch": True},
    {"code": "es", "name": "Spanish",    "native": "Español",    "launch": True},
    {"code": "fr", "name": "French",     "native": "Français",   "launch": True},
    {"code": "de", "name": "German",     "native": "Deutsch",    "launch": True},
    {"code": "nl", "name": "Dutch",      "native": "Nederlands", "launch": True},
    {"code": "it", "name": "Italian",    "native": "Italiano",   "launch": True},
    {"code": "pt", "name": "Portuguese", "native": "Português",  "launch": True},
    {"code": "pl", "name": "Polish",     "native": "Polski",     "launch": True},
    {"code": "sv", "name": "Swedish",    "native": "Svenska",    "launch": True},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia", "launch": True},
    {"code": "zh", "name": "Chinese",    "native": "中文",        "launch": False},
    {"code": "ja", "name": "Japanese",   "native": "日本語",      "launch": False},
    {"code": "ar", "name": "Arabic",     "native": "العربية",     "launch": False},
]

# Shared clause every image prompt ends with, whatever the style.
_SUFFIX = ("Full-bleed image, no borders, absolutely no text, letters, words, "
           "captions or signatures anywhere.")

STYLE_PRESETS = [
    {"id": "ink-wash", "name": "Ink & wash", "realistic": False,
     "prompt": ("Cinematic illustration in a muted ink-and-wash style, fine black "
                "linework with cross-hatching over painted colour, strong chiaroscuro "
                "with one dominant light source and deep shadows. " + _SUFFIX)},
    {"id": "realistic", "name": "Realistic", "realistic": True,
     "prompt": ("Photorealistic cinematic still, natural lighting, shallow depth of "
                "field, subtle film grain, lifelike detail and skin texture. " + _SUFFIX)},
    {"id": "watercolor", "name": "Watercolour storybook", "realistic": False,
     "prompt": ("Soft watercolour storybook illustration, gentle washes, visible paper "
                "texture, warm tender palette, rounded gentle forms. " + _SUFFIX)},
    {"id": "anime", "name": "Anime / manga", "realistic": False,
     "prompt": ("Modern anime illustration, clean cel shading, expressive eyes, a soft "
                "but vivid palette and detailed painted backgrounds. " + _SUFFIX)},
    {"id": "graphic-novel", "name": "Graphic novel", "realistic": False,
     "prompt": ("Bold graphic-novel ink art, heavy inking, halftone shading, high "
                "contrast and dramatic full-bleed composition. " + _SUFFIX)},
    {"id": "render-3d", "name": "3D render", "realistic": False,
     "prompt": ("Stylized 3D render, soft global illumination, subsurface skin "
                "scattering, warm cinematic lighting and shallow depth of field. " + _SUFFIX)},
    {"id": "noir", "name": "Film noir", "realistic": False,
     "prompt": ("High-contrast black-and-white film-noir illustration, deep shadows, "
                "hard key light and a moody rain-slicked atmosphere. " + _SUFFIX)},
    {"id": "oil", "name": "Oil painting", "realistic": False,
     "prompt": ("Classical oil painting, visible brushwork, rich chiaroscuro, warm "
                "varnished tones and museum lighting. " + _SUFFIX)},
]

# Which engine renders images / speaks narration. `key` = the BYOK provider needed
# (None = free, no key). The app lets the user pick per project.
IMAGE_PROVIDERS = [
    {"id": "pollinations", "name": "Pollinations (free)", "key": None,     "free": True},
    {"id": "gemini",       "name": "Gemini · Nano Banana", "key": "gemini", "free": False},
    {"id": "openai",       "name": "OpenAI · GPT Image",   "key": "openai", "free": False},
]
AUDIO_PROVIDERS = [
    {"id": "edge",       "name": "Edge voices (free)", "key": None,         "free": True},
    {"id": "fish",       "name": "Fish Audio",         "key": "fish",       "free": False},
    {"id": "openai",     "name": "OpenAI TTS",         "key": "openai",     "free": False},
    {"id": "elevenlabs", "name": "ElevenLabs",         "key": "elevenlabs", "free": False},
]

# Claude models the user can pick per task (needs their Anthropic key). "custom" lets
# them type any exact model id their account supports (e.g. an older Opus 4.x id).
LLM_MODELS = [
    {"id": "claude-opus-5", "name": "Claude Opus 5 (best quality)"},
    {"id": "claude-sonnet-5", "name": "Claude Sonnet 5 (balanced)"},
    {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5 (fast, cheap)"},
    {"id": "claude-fable-5-1", "name": "Claude Fable 5.1"},
    {"id": "custom", "name": "Custom model id…"},
]
_DEFAULT_LLM = "claude-sonnet-5"


def llm_model(mid, custom=None):
    """Resolve a chosen model to a real id. 'custom' uses the typed id; any id that
    looks like a Claude model is allowed through so new/older versions still work."""
    if mid == "custom" and custom and custom.strip():
        return custom.strip()
    ids = {m["id"] for m in LLM_MODELS}
    if mid in ids and mid != "custom":
        return mid
    if isinstance(mid, str) and mid.startswith("claude-"):
        return mid
    return _DEFAULT_LLM


# Render engines the user can pick at the render step (step 2). ffmpeg is the default
# (light, cheap, scales to long videos); Remotion is the premium cinematic engine
# (needs the render worker with Node+Chrome and a Remotion licence).
RENDER_ENGINES = [
    {"id": "ffmpeg", "name": "Standard (ffmpeg)", "premium": False,
     "tagline": "Clean pan & zoom with burned captions — fast, reliable, great for long videos.",
     "pros": ["Fast and low-cost", "Handles 30–60 min videos", "Always available"],
     "cons": ["Simple motion (Ken Burns)", "Captions are burned-in, not animated"]},
    {"id": "remotion", "name": "Cinematic (Remotion)", "premium": True,
     "tagline": "Animated captions, transitions and motion graphics — the premium look.",
     "pros": ["Animated word-by-word captions", "Transitions & motion graphics", "Fully designed look"],
     "cons": ["Slower and more expensive to render", "Best for shorter videos", "Premium — must be enabled"]},
]
_ENGINE_IDS = {e["id"] for e in RENDER_ENGINES}


def render_engine(eid):
    return eid if eid in _ENGINE_IDS else "ffmpeg"


# When the engine is Remotion, WHERE it renders. worker = our render worker (Chrome,
# no AWS, great for Shorts, slow for long videos). lambda = AWS Lambda (renders long
# videos in minutes, scales, but needs AWS setup and costs more per video).
REMOTION_BACKENDS = [
    {"id": "worker", "name": "Built-in worker", "premium": False,
     "tagline": "No AWS needed. Best for Shorts.",
     "pros": ["Works out of the box", "Free to run"],
     "cons": ["Slow for long videos (10 min ≈ 30–60 min to render)"]},
    {"id": "lambda", "name": "AWS Lambda", "premium": True,
     "tagline": "Renders a 10-min video in ~1 minute. Best for long videos.",
     "pros": ["Massively parallel — long videos in minutes", "Scales to many users at once"],
     "cons": ["Needs a one-time AWS setup", "Costs a few cents of AWS per render"]},
]
_BACKEND_IDS = {b["id"] for b in REMOTION_BACKENDS}


def remotion_backend(bid):
    return bid if bid in _BACKEND_IDS else "worker"


# Output resolution the user picks at the render step. `p` = the short edge (the "…p"
# number): 1080p landscape = 1920x1080, 1080p portrait (Short) = 1080x1920, etc.
RESOLUTIONS = [
    {"p": 1080, "name": "1080p · Full HD", "tag": "Sharpest — best for Shorts/Reels/TikTok"},
    {"p": 720,  "name": "720p · HD",       "tag": "Balanced — quicker for long videos"},
    {"p": 480,  "name": "480p · SD",       "tag": "Smallest & fastest — quick drafts"},
]
_RES = {r["p"] for r in RESOLUTIONS}
DEFAULT_RES = 1080


def resolution(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return DEFAULT_RES
    return p if p in _RES else DEFAULT_RES


def default_resolution(fmt_id):
    """Long videos default to 720p (many images → far cheaper to render); Shorts to 1080p."""
    return 720 if fmt_id == "long" else 1080


def _even2(x):
    x = int(round(x))
    return x - (x % 2)


def video_dims(fmt_id, p):
    """(width, height) for a format + chosen resolution. p is the short edge."""
    p = resolution(p)
    long_edge = _even2(p * 16 / 9)
    if fmt_id == "short":
        return (_even2(p), long_edge)      # portrait 9:16 — width = p
    return (long_edge, _even2(p))          # landscape 16:9 — height = p


# Video formats: landscape long-form vs vertical Short. `img` = the source image size
# (generated big enough to stay sharp up to 1080p output); the final video size comes
# from video_dims(format, resolution). `sec_per_image` drives the auto image count.
FORMATS = {
    "long":  {"name": "Long video (16:9)", "img": (1920, 1080), "sec_per_image": 20},
    "short": {"name": "Short (9:16)",      "img": (1080, 1920), "sec_per_image": 5},
}


def fmt(f):
    return FORMATS.get(f, FORMATS["long"])


_STYLE_BY_ID = {s["id"]: s for s in STYLE_PRESETS}
_LANG_BY_CODE = {l["code"]: l for l in LANGUAGES}
_IMG_BY_ID = {p["id"]: p for p in IMAGE_PROVIDERS}
_AUD_BY_ID = {p["id"]: p for p in AUDIO_PROVIDERS}


def image_provider(pid):
    return _IMG_BY_ID.get(pid) or _IMG_BY_ID["pollinations"]


def audio_provider(pid):
    return _AUD_BY_ID.get(pid) or _AUD_BY_ID["edge"]


def style_prompt(style_id, custom_text=None):
    """Return the image-prompt prefix for a preset id, or a custom description."""
    if style_id == "custom" and custom_text:
        return f"{custom_text.strip().rstrip('.')}. {_SUFFIX}"
    s = _STYLE_BY_ID.get(style_id)
    return s["prompt"] if s else _STYLE_BY_ID["ink-wash"]["prompt"]


def is_language_supported(code):
    l = _LANG_BY_CODE.get(code)
    return bool(l and l["launch"])
